# --------------------------------------------------------------------
# shell.py: Shell command execution tools, including ShellRecipe.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Generator, List, Optional, Tuple, Union

from ansilog import bg, fg

from .config import CPU_CORES
from .errors import BuildError
from .recipes import FileRecipe
from .reports import Report
from .util import digest_env, format_dt, get_logger, is_iterable, decode

# -------------------------------------------------------------------
LineSinkFunction = Callable[[str], None]
ShellOutputTaskData = Tuple[asyncio.StreamReader, LineSinkFunction]


# --------------------------------------------------------------------
log = get_logger("panifex")


# --------------------------------------------------------------------
@dataclass
class OutputLine:
    stderr: bool
    line: str
    when: datetime = field(default_factory=lambda: datetime.now())

    def json(self):
        result = {"when": format_dt(self.when), "line": self.line}

        if self.stderr:
            result["error"] = True

        return result

    def __str__(self):
        return self.line


# -------------------------------------------------------------------
class OutputSink:
    def out(self, line):
        raise NotImplementedError()

    def err(self, line):
        raise NotImplementedError()

    def output(self) -> Generator[OutputLine, None, None]:
        raise NotImplementedError()


# -------------------------------------------------------------------
class InMemoryOutputSink(OutputSink):
    def __init__(self):
        self._output = []

    def out(self, line):
        self._output.append(OutputLine(False, line))

    def err(self, line):
        self._output.append(OutputLine(True, line))

    def output(self) -> Generator[OutputLine, None, None]:
        yield from sorted(self._output, key=lambda x: x.when)


# -------------------------------------------------------------------
class NullOutputSink(OutputSink):
    def output(self) -> Generator[OutputLine, None, None]:
        yield from ()


# -------------------------------------------------------------------
class PostCommunicateOutputSink(OutputSink):
    def __init__(self, stdout: str, stderr: str):
        self._stdout = stdout
        self._stderr = stderr

    def output(self) -> Generator[OutputLine, None, None]:
        yield from (OutputLine(False, line) for line in self._stdout.splitlines())
        yield from (OutputLine(True, line) for line in self._stderr.splitlines())


# -------------------------------------------------------------------
class OutputCollector:
    async def collect(self, proc: Any) -> OutputSink:
        raise NotImplementedError()


# -------------------------------------------------------------------
class ShellOutputCollector:
    # pylint/issues/1469: pylint doesn't recognize asyncio.subprocess
    # pylint: disable=E1101
    def __init__(self):
        self._readline_tasks: Dict[asyncio.Future[Any], ShellOutputTaskData] = {}

    def _setup_readline_task(
        self, stream: asyncio.StreamReader, sink: Callable[[str], None]
    ):
        if stream is not None:
            self._readline_tasks[asyncio.Task(stream.readline())] = (stream, sink)

    async def collect(self, proc: Any, sink: OutputSink):
        if not isinstance(proc, asyncio.subprocess.Process):
            raise ValueError("`proc` is not an asyncio.subprocess.Process object.")
        if hasattr(proc, "stdout") and proc.stdout is not None:
            self._setup_readline_task(proc.stdout, sink.out)
        if hasattr(proc, "stderr") and proc.stderr is not None:
            self._setup_readline_task(proc.stderr, sink.err)

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
class ShellCommunicateOutputCollector(OutputCollector):
    async def collect(self, proc: Any) -> OutputSink:
        if not isinstance(proc, subprocess.Popen):
            raise ValueError("`proc` is not a subprocess.Popen object.")

        return PostCommunicateOutputSink(*proc.communicate())


# --------------------------------------------------------------------
@dataclass
class ShellReport(Report):
    name: str
    started: Optional[datetime]
    finished: Optional[datetime]
    cmd: str
    sink: Optional[OutputSink]
    returncode: Optional[int]

    def succeeded(self):
        return self.returncode == 0

    def generate(self):
        return {
            **super().generate(),
            "cmd": self.cmd,
            "returncode": self.returncode,
            "out": [line.json() for line in self.sink.output() if not line.stderr]
            if self.sink
            else [],
            "err": [line.json() for line in self.sink.output() if line.stderr]
            if self.sink
            else [],
        }

    def output(self, stdout=True, stderr=False) -> Generator[OutputLine, None, None]:
        if self.sink is None:
            return

        for line in self.sink.output():
            if not line.stderr and stdout:
                yield line
            elif line.stderr and stderr:
                yield line

    def log_output(self, stdout=True, stderr=True, log=log):
        if self.sink is None:
            log.info("<no output>")
            return

        for line in self.sink.output():
            if not line.stderr and stdout:
                log.info(line.line)

        for line in self.sink.output():
            if line.stderr and stderr:
                log.info(fg.red(line.line))


# --------------------------------------------------------------------
class ShellFailed(BuildError):
    def __init__(self, report: ShellReport):
        super().__init__(f"{report.name} failed.")
        self.report = report


# -------------------------------------------------------------------
class ShellRecipe(FileRecipe):
    OUT = "output"
    IN = "input"
    INCLUDES = "includes"
    CWD = "cwd"
    _limiter = asyncio.BoundedSemaphore(CPU_CORES)

    def __init__(self, command, **params):
        super().__init__()

        self._input = params.get(self.IN, None)
        self._includes = params.get(self.INCLUDES, None)
        self._output = params.get(self.OUT, None)
        self._cwd = params.get(self.CWD, os.getcwd())
        self._env = {}
        self._params = {**params}
        self._name = "Shell Command"
        self._sink: Optional[OutputSink] = None
        self._returncode = 0
        self._cmd = shlex.join(command) if isinstance(command, (list, tuple)) else command
        self._user_input: Optional[str] = None
        self._interactive = False
        self._echo = True

    def with_env(self, env: Dict):
        self.merge_env(env)
        return self

    def with_name(self, name: str):
        self._name = name
        return self

    def with_sink(self, sink: OutputSink):
        self._sink = sink

    def with_user_input(self, input: str):
        self._user_input = input
        return self

    def no_echo(self):
        self._echo = False
        return self

    def __repr__(self):
        return f"<panifex.ShellRecipe {self._cmd}, {self._params}>"

    def _check_success(self):
        if not self.succeeded():
            raise ShellFailed(self.report())

    def succeeded(self):
        return self.is_done() and self._returncode == 0

    def merge_env(self, env):
        self._env.update(env)
        return self

    def interactive(self):
        self._interactive = True
        return self

    def user_input(self, input):
        self._user_input = input
        return self

    async def _resolve(self) -> Any:
        await self._run_command(self._cmd)
        return self.output()

    async def _run_command(self, cmd) -> None:
        await self._limiter.acquire()
        try:
            params, args, decorated_args = self._parse_command(cmd)
            if self._echo:
                log.info(fg.blue("[sh]") + decorated_args)

            if self._interactive:
                if self._user_input:
                    raise ValueError(
                        "Interactive shell can't provide input programmatically."
                    )
                self._sink = NullOutputSink()
                self._returncode = subprocess.call(
                    self._cmd, env=digest_env(params), cwd=self._cwd, shell=True
                )

            else:
                proc = await asyncio.create_subprocess_shell(
                    self._cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=digest_env(params),
                    cwd=self._cwd,
                )

                if self._user_input is not None and proc.stdin is not None:
                    proc.stdin.write(self._user_input.encode('utf-8'))
                    await proc.stdin.drain()
                    proc.stdin.close()

                collector = ShellOutputCollector()
                self._sink = InMemoryOutputSink()
                await collector.collect(proc, self._sink)
                await proc.wait()
                self._returncode = proc.returncode

            self.finish()
            if self._echo:
                self._print_run_report(decorated_args)

        finally:
            self._limiter.release()

    def _parse_command(self, cmd):
        params = {**self._params, **self._env}

        for k, v in params.items():
            if is_iterable(v):
                params[k] = " ".join([shlex.quote(str(x)) for x in v])
            else:
                params[k] = shlex.quote(str(v))

        self._cmd = cmd.format(**params)
        args = shlex.split(self._cmd)

        decorated_args = f" {fg.magenta(args[0])} {shlex.join(args[1:])}"

        return params, args, decorated_args

    def _run_command_sync(self, cmd):
        params, args, decorated_args = self._parse_command(cmd)
        if self._echo:
            self._print_run_header(decorated_args)

        if self._interactive:
            if self._user_input:
                raise ValueError(
                    "Interactive shell can't provide input programmatically."
                )
            self._sink = NullOutputSink()
            self._returncode = subprocess.call(
                self._cmd, env=digest_env(params), cwd=self._cwd, shell=True
            )
        else:
            proc = subprocess.Popen(
                shlex.split(self._cmd),
                env=digest_env(params),
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                text=True
            )
            stdout, stderr = proc.communicate(input=self._user_input)
            self._sink = PostCommunicateOutputSink(stdout, stderr)
            self._returncode = proc.returncode

        self.finish()
        if self._echo:
            self._print_run_report(decorated_args)

    @classmethod
    def _print_run_header(cls, decorated_args):
        log.info(fg.blue("[sh]") + decorated_args)

    def _print_run_report(self, decorated_args):
        if self.succeeded():
            if self.config and self.config.verbose:
                self.report().log_output()
        else:
            log.info(fg.white(bg.red("[!!]")) + decorated_args)
            self.report().log_output()

    def input(self) -> Any:
        return [self._input, self._includes]

    def output(self) -> Any:
        return self._output

    def report(self) -> ShellReport:
        return ShellReport(
            name=self._name,
            started=self.started,
            finished=self.finished,
            cmd=self._cmd,
            sink=self._sink,
            returncode=self._returncode,
        )

    def sync(self) -> 'ShellRecipe':
        self._run_command_sync(self._cmd)
        return self


# -------------------------------------------------------------------
class ShellRecipeFactory:
    def __init__(self):
        self._env = {**os.environ}

    def clone(self) -> 'ShellRecipeFactory':
        sh = ShellRecipeFactory()
        sh.env(**self._env)
        return sh

    def env(self, *args, **kwargs) -> Union[str, List[str]]:
        if kwargs:
            self._env.update(kwargs)
        if args is not None:
            if len(args) == 1:
                return self._env[args[0]]
            return [self._env[k] for k in args]
        return {**self.env}

    def __getitem__(self, name):
        return self.env(name)

    def __setitem__(self, name, value):
        self.env(**{name: value})

    def __call__(self, *args, **kwargs):
        recipe = ShellRecipe(*args, **kwargs)
        recipe.merge_env(self._env)
        return recipe


# -------------------------------------------------------------------
sh = ShellRecipeFactory()
