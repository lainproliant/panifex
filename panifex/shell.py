# --------------------------------------------------------------------
# shell.py: Shell command execution tools, including ShellRecipe.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
import itertools
import os
import shlex
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from .config import CPU_CORES
from .recipes import Artifact, File, Recipe
from .util import decode, is_iterable

# -------------------------------------------------------------------
LineSinkFunction = Callable[[str], None]
OutputTaskData = Tuple[asyncio.StreamReader, LineSinkFunction]


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
    def __init__(self, files: List[File] = [], stdout=True, stderr=False):
        self.returncode: Optional[int] = None
        self._files = files
        self._stdout = stdout
        self._stderr = stderr
        self.output: Optional[OutputSink] = None

    @property
    def exists(self) -> bool:
        return self.returncode is not None and all(f.exists for f in self._files)

    @property
    def age(self) -> timedelta:
        return min(f.age for f in self._files) if self._files else timedelta.max

    async def clean(self):
        await asyncio.gather(*(f.clean() for f in self._files))

    def to_param(self):
        if self._files:
            return [*itertools.chain(*[f.to_param() for f in self._files])]
        if self.output is not None:
            return [
                line.line
                for line in self.output.lines(stdout=self._stdout, stderr=self._stderr)
            ]
        raise ValueError("ShellResult has no results.")


# -------------------------------------------------------------------
class ShellRecipe(Recipe):
    _limiter = asyncio.BoundedSemaphore(CPU_CORES)

    def __init__(
        self,
        cmd: str,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = {},
        input: Optional[str] = None,
        outputs: Optional[List[File]] = None,
        stdout=True,
        stderr=False,
        requires: Optional[List[Recipe]] = None,
    ):
        super().__init__(requires)
        self._cmd = cmd
        self._cwd = cwd or Path.cwd()
        self._env = env or {}
        self._outputs = outputs or []
        self._input = input
        self._result = ShellResult(self._outputs, stdout=stdout, stderr=stderr)

    @property
    def creates(self) -> List[Artifact]:
        return [self._result]

    async def make(self):
        await self._limiter.acquire()
        try:
            proc = await asyncio.create_subprocess_shell(
                self._cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=self._env,
                shell=True,
            )

            if self._input is not None and proc.stdin is not None:
                proc.stdin.write(self._input.encode("utf-8"))

            collector = AsyncOutputCollector()
            sink = InMemoryOutputSink()
            await collector.collect(proc, sink)
            await proc.wait()
            self._result.returncode = proc.returncode
            self._result.output = sink

        finally:
            self._limiter.release()


# -------------------------------------------------------------------
class InteractiveShellRecipe(ShellRecipe):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self._input is not None:
            raise ValueError("Interactive shell can't provide input programmatically.")

    async def make(self):
        self._result.returncode = subprocess.call(
            self._cmd, cwd=self._cwd, env=self._env, shell=True
        )
        self._result.output = NullOutputSink()


# -------------------------------------------------------------------
class ShellFactory:
    OUTPUT = "output"

    def __init__(self, env: Optional[Dict[str, str]] = None):
        self._env = {**os.environ, **(env or {})}

    def env(self, **kwargs):
        return ShellFactory({**self._env, **kwargs})
        self._env.update(kwargs)

    def __call__(
        self,
        cmd,
        stdout=True,
        stderr=False,
        cwd: Optional[Path] = None,
        env: Optional[Dict[str, str]] = None,
        input: Optional[str] = None,
        output: Optional[Union[File, List[File]]] = None,
        requires: Optional[List[Recipe]] = None,
        interactive=False,
        echo=True,
        **kwargs
    ):
        params = {**kwargs}
        if isinstance(output, File):
            output = [output]
        if isinstance(output, list):
            params[self.OUTPUT] = " ".join(shlex.quote(f.to_param()) for f in output)

        env = {**self._env, **(env or {})}

        for k, v in {**kwargs, **env, "output": output}.items():
            if is_iterable(v):
                params[k] = " ".join([shlex.quote(str(x)) for x in v])
            else:
                params[k] = shlex.quote(str(v))

        cls = ShellRecipe
        if interactive:
            cls = InteractiveShellRecipe

        return cls(
            cmd=cmd.format(**params),
            cwd=cwd,
            env=env,
            input=input,
            outputs=output,
            stdout=stdout,
            stderr=stderr,
            requires=requires
        )


# --------------------------------------------------------------------
sh = ShellFactory()


# --------------------------------------------------------------------
def check(cmd):
    return subprocess.check_output(shlex.split(cmd)).decode("utf-8").strip()
