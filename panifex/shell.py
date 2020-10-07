# --------------------------------------------------------------------
# shell.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
import os
import shlex
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Set, Tuple, Union

from ansilog import fg

from .artifacts import Artifact, NullArtifact, PolyArtifact
from .config import Config
from .errors import BuildError
from .files import FileArtifact, as_artifact
from .params import EnvironmentDict, digest_env, digest_param, digest_param_map
from .recipes import Recipe
from .util import decode, is_iterable

# -------------------------------------------------------------------
LineSinkFunction = Callable[[str], None]
OutputTaskData = Tuple[asyncio.StreamReader, LineSinkFunction]
ArtifactOrPath = Union[str, Path, Artifact]

# --------------------------------------------------------------------
log = Config.get().get_logger(__name__)


# --------------------------------------------------------------------
def check(cmd):
    return subprocess.check_output(shlex.split(cmd)).decode("utf-8").strip()


# --------------------------------------------------------------------
class OutputLine:
    def __init__(self, stderr: bool, line: str, when: Optional[datetime] = None):
        self.stderr = stderr
        self.line = line
        self.when = when or datetime.now()

    def __str__(self):
        return self.line


# -------------------------------------------------------------------
class OutputSink:
    def output(self, line):
        raise NotImplementedError()

    def error(self, line):
        raise NotImplementedError()

    def lines(self, stdout=True, stderr=False) -> Generator[OutputLine, None, None]:
        raise NotImplementedError()


# -------------------------------------------------------------------
class InMemoryOutputSink(OutputSink):
    def __init__(self):
        self._lines: List[OutputLine] = []

    def output(self, line):
        self._lines.append(OutputLine(False, line))

    def error(self, line):
        self._lines.append(OutputLine(True, line))

    def lines(self, stdout=True, stderr=False) -> Generator[OutputLine, None, None]:
        for line in self._lines:
            if (not line.stderr and stdout) or (line.stderr and stderr):
                yield line


# -------------------------------------------------------------------
class NullOutputSink(OutputSink):
    def lines(self, stdout=True, stderr=False) -> Generator[OutputLine, None, None]:
        yield from ()


# -------------------------------------------------------------------
class PostCommunicateOutputSink(OutputSink):
    def __init__(self, stdout: str, stderr: str):
        self._stdout = stdout
        self._stderr = stderr

    def lines(self, stdout=True, stderr=False) -> Generator[OutputLine, None, None]:
        if stdout:
            yield from (OutputLine(False, line) for line in self._stdout.splitlines())
        if stderr:
            yield from (OutputLine(True, line) for line in self._stderr.splitlines())


# -------------------------------------------------------------------
class OutputCollector:
    async def collect(self, proc: Any, sink: OutputSink):
        raise NotImplementedError()


# -------------------------------------------------------------------
class AsyncOutputCollector(OutputCollector):
    # pylint/issues/1469: pylint doesn't recognize asyncio.subprocess
    # pylint: disable=E1101
    def __init__(self):
        self._readline_tasks: Dict[asyncio.Future[Any], OutputTaskData] = {}

    def _setup_readline_task(
        self, stream: asyncio.StreamReader, sink: Callable[[str], None]
    ):
        if stream is not None:
            self._readline_tasks[asyncio.Task(stream.readline())] = (stream, sink)

    async def collect(self, proc: Any, sink: OutputSink):
        if not isinstance(proc, asyncio.subprocess.Process):
            raise ValueError("`proc` is not an asyncio.subprocess.Process object.")
        if hasattr(proc, "stdout") and proc.stdout is not None:
            self._setup_readline_task(proc.stdout, sink.output)
        if hasattr(proc, "stderr") and proc.stderr is not None:
            self._setup_readline_task(proc.stderr, sink.error)

        while self._readline_tasks:
            done, pending = await asyncio.wait(
                self._readline_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            for future in done:
                stream, sink_f = self._readline_tasks.pop(future)
                line = future.result()
                if line:
                    line = decode(line).strip()
                    sink_f(line)
                    self._setup_readline_task(stream, sink_f)


# -------------------------------------------------------------------
class ShellResult(Artifact):
    def __init__(self, file: Artifact = NullArtifact()):
        if not (file.is_null or isinstance(file, FileArtifact)):
            raise ValueError("File must be null or a FileArtifact.")
        self._returncode: Optional[int] = None
        self._file = file
        self._sink: OutputSink = NullOutputSink()

    @property
    def returncode(self) -> int:
        if self._returncode is None:
            raise ValueError("Return code has not yet been received.")
        return self._returncode

    @returncode.setter
    def returncode(self, code: int):
        if self._returncode is not None:
            raise ValueError("Return code has already been set.")
        self._returncode = code

    @property
    def has_returncode(self) -> bool:
        return self._returncode is not None

    @property
    def exists(self) -> bool:
        return self._file.exists

    @property
    def file(self) -> Artifact:
        return self._file

    @property
    def sink(self) -> OutputSink:
        return self._sink

    @sink.setter
    def sink(self, output_sink: OutputSink):
        self._sink = output_sink

    @property
    def stdout(self) -> List[str]:
        return list([l.line for l in self._sink.lines(stdout=True, stderr=False)])

    @property
    def stderr(self) -> List[str]:
        return list([l.line for l in self._sink.lines(stdout=False, stderr=True)])

    @property
    def age(self) -> timedelta:
        if not self.file.is_null:
            return self.file.age
        return timedelta.max

    def to_params(self) -> List[str]:
        return self.file.to_params()

    async def clean(self):
        await self.file.clean()

    def __repr__(self):
        return "<{%s} (%s) [%s]}>" % (
            self.__class__.__name__,
            self.returncode if self.has_returncode else "?",
            self.file,
        )


# -------------------------------------------------------------------
class ShellRecipe(Recipe):
    _limiter = asyncio.BoundedSemaphore(Config.get().cpu_cores)

    def __init__(
        self,
        cmd: str,
        cwd: Optional[Path] = None,
        env: Optional[EnvironmentDict] = {},
        to_stdin: Optional[str] = None,
        output: Optional[ArtifactOrPath] = None,
        input: Any = None,
        requires: Any = None,
        echo: bool = True,
        success_codes: Set[int] = {0},
    ):
        input_recipes = []
        input_artifacts = []

        if input is not None and is_iterable(input):
            for item in input:
                if isinstance(item, Recipe):
                    input_recipes.append(item)
                else:
                    input_artifacts.append(as_artifact(item))
        else:
            if isinstance(input, Recipe):
                input_recipes.append(input)
            else:
                input_artifacts.append(as_artifact(input))

        super().__init__(input_recipes)
        self._cmd = cmd
        self._cwd = cwd or Path.cwd()
        self._env = env or {}
        self._inputs = input_artifacts
        self._echo = echo
        self._to_stdin: Optional[str] = to_stdin
        self._result = ShellResult(as_artifact(output, True))
        self._success_codes = success_codes

    @property
    def display_info(self) -> str:
        return self._interpolate_cmd()

    @property
    def is_done(self) -> bool:
        if self._result.file.is_null:
            return (
                self._result._returncode is not None
                and self._result._returncode in self._success_codes
            )
        return Recipe.is_done.fget(self)

    @property
    def ansi_input_display(self) -> Optional[str]:
        if not self.input.is_null:
            return f"{fg.blue(', '.join(digest_param(self.input, Path.cwd())))}"
        return None

    @property
    def ansi_output_display(self) -> Optional[str]:
        if not self.output.is_null:
            return f"{fg.green(', '.join(digest_param(self.output, Path.cwd())))}"
        return None

    @property
    def ansi_display_info(self) -> str:
        args = shlex.split(self._interpolate_cmd(colorize=True))
        return f"{fg.magenta(args[0])} {' '.join(str(arg) for arg in args[1:])}"

    @property
    def output(self) -> Artifact:
        return self._result

    @property
    def input(self) -> Artifact:
        return PolyArtifact([Recipe.input.fget(self), *self._inputs])

    def _interpolate_cmd(self, colorize=False) -> str:
        input_param = shlex.join(digest_param(self.input, self._cwd))
        output_param = shlex.join(digest_param(self.output, self._cwd))

        if colorize:
            input_param = fg.cyan(input_param)
            output_param = fg.green(output_param)

        return self._cmd.format(**{"input": input_param, "output": output_param})

    async def make(self):
        log.debug("Entering ShellRecipe.make()")
        config = Config.get()
        if self._result.has_returncode:
            if self._result.returncode in self._success_codes:
                log.debug("ShellRecipe has already been completed.")
                return
            raise BuildError("ShellRecipe has failed previously.")

        try:
            await self._limiter.acquire()
            proc = await asyncio.create_subprocess_shell(
                self._interpolate_cmd(),
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=digest_env(self._env),
                shell=True,
            )

            if self._to_stdin is not None and proc.stdin is not None:
                proc.stdin.write(self._to_stdin.encode("utf-8"))

            collector = AsyncOutputCollector()
            sink = InMemoryOutputSink()
            await collector.collect(proc, sink)
            await proc.wait()
            self._result.returncode = proc.returncode
            self._result.sink = sink
            if self._result.returncode not in self._success_codes:
                for line in self._result.stderr:
                    self.log_error(line)
                raise BuildError(
                    "ShellCommand has failed (returncode: %d)" % self._result.returncode
                )

            if config.verbose:
                for line in self._result.stdout:
                    self.log_info(line)
                for line in self._result.stderr:
                    self.log_error(line)

        except Exception as e:
            raise e

        finally:
            self._limiter.release()


# -------------------------------------------------------------------
class InteractiveShellRecipe(ShellRecipe):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "sh"
        if self._to_stdin is not None:
            raise ValueError(
                "Interactive shell can't provide to_stdin programmatically."
            )

    @property
    def output(self) -> Artifact:
        return NullArtifact()

    async def make(self):
        self._result.returncode = subprocess.call(
            self._interpolate_cmd(),
            cwd=self._cwd,
            env=digest_env(self._env),
            shell=True,
        )
        self._result.sink = NullOutputSink()
        if self._result.returncode not in self._success_codes:
            raise BuildError(
                "ShellCommand has failed (returncode: %d)" % self._result.returncode
            )


# -------------------------------------------------------------------
class ShellFactory:
    def __init__(self, env: Optional[EnvironmentDict] = None):
        self._env: EnvironmentDict = {**os.environ, **(env or {})}

    def env(self, **kwargs):
        return ShellFactory({**self._env, **kwargs})
        self._env.update(kwargs)

    def __call__(
        self,
        cmd,
        cwd: Optional[Path] = None,
        env: Optional[EnvironmentDict] = None,
        to_stdin: Optional[str] = None,
        output: Optional[ArtifactOrPath] = None,
        input: Any = None,
        requires: Any = None,
        interactive=False,
        echo=True,
        **kwargs,
    ):
        output = as_artifact(output, True)

        cls = ShellRecipe
        if interactive:
            cls = InteractiveShellRecipe

        env = {**self._env, **(env or {})}

        return cls(
            cmd=cmd.format(**digest_param_map({**kwargs, **env}), input="{input}", output="{output}"),
            cwd=cwd,
            env=env,
            to_stdin=to_stdin,
            output=output,
            input=input,
            requires=requires,
            echo=echo,
        )


# --------------------------------------------------------------------
sh = ShellFactory()
