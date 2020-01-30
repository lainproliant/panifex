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
from ansilog import fg, bg

from .config import CPU_CORES
from .errors import BuildError
from .recipes import FileRecipe
from .reports import Report
from .util import digest_env, format_dt, get_logger, is_iterable

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
class EmptyOutputSink(OutputSink):
    def output(self) -> Generator[OutputLine, None, None]:
        yield from ()


# -------------------------------------------------------------------
class PostMortemOutputSink(OutputSink):
    def __init__(self, stdout: str, stderr: str):
        self._stdout = stdout
        self._stderr = stderr

    def output(self) -> Generator[OutputLine, None, None]:
        for line in self._stdout.splitlines():
            yield OutputLine(False, line)
        for line in self._stderr.splitlines():
            yield OutputLine(True, line)


# -------------------------------------------------------------------
class OutputCollector:
    async def collect():
        # TODO
        pass

# -------------------------------------------------------------------
class ProcessCommunicateCollector:
    pass

# -------------------------------------------------------------------
class ShellOutputCollector:
    # pylint/issues/1469: pylint doesn't recognize asyncio.subprocess
    # pylint: disable=E1101
    def __init__(
        self, proc: asyncio.subprocess.Process, sink: Optional[OutputSink] = None
    ):
        self._proc = proc
        self._readline_tasks: Dict[asyncio.Future[Any], ShellOutputTaskData] = {}
        if sink is None:
            sink = InMemoryOutputSink()
        self._sink = sink

    def _setup_readline_task(
        self, stream: asyncio.StreamReader, sink: Callable[[str], None]
    ):
        if stream is not None:
            self._readline_tasks[asyncio.Task(stream.readline())] = (stream, sink)

    async def collect(self) -> OutputSink:
        if self._proc.stdout is not None:
            self._setup_readline_task(self._proc.stdout, self._sink.out)
        if self._proc.stderr is not None:
            self._setup_readline_task(self._proc.stderr, self._sink.err)

        while self._readline_tasks:
            done, pending = await asyncio.wait(
                self._readline_tasks, return_when=asyncio.FIRST_COMPLETED
            )

            for future in done:
                stream, sink = self._readline_tasks.pop(future)
                line = future.result()
                if line:
                    line = line.decode("utf-8").strip()
                    sink(line)
                    self._setup_readline_task(stream, sink)

        return self._sink


# --------------------------------------------------------------------
@dataclass
class SubprocessReport(Report):
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
            "out": [line.json() for line in self.sink.output() if not line.stderr] if self.sink else [],
            "err": [line.json() for line in self.sink.output() if line.stderr] if self.sink else [],
        }

    def log_output(self, stdout=True, stderr=True):
        if not self.sink:
            log.info("<no output>")
            return

        for line in self.sink.output():
            if not line.stderr and stdout:
                log.info(line.line)

        for line in self.sink.output():
            if line.stderr and stderr:
                log.info(fg.red(line.line))


# -------------------------------------------------------------------
class ShellRecipe(FileRecipe):
    OUT = "output"
    IN = "input"
    CWD = "cwd"
    _limiter = asyncio.BoundedSemaphore(CPU_CORES)

    def __init__(self, command, **params):
        super().__init__()

        self._input = params.get(self.IN, None)
        self._output = params.get(self.OUT, None)
        self._cwd = params.get(self.CWD, os.getcwd())
        self._env = {}
        self._command = command
        self._params = {**params}
        self._name = "Shell Command"
        self._user_input = None
        self._interactive = False

        if "__name__" in self._params:
            self._name = self._params["__name__"]
            del self._params["__name__"]

        self._sink: Optional[OutputSink] = None
        self._returncode = 0
        self._cmd = " ".join(self._command)

    def __repr__(self):
        return f"<panifex.ShellRecipe {self._command}, {self._params}>"

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
        await self._run_command(self._command)
        return self.output()

    async def _run_command(self, cmd) -> None:
        await self._limiter.acquire()
        try:
            params = {**self._params, **self._env}

            for k, v in params.items():
                if is_iterable(v):
                    params[k] = " ".join([shlex.quote(str(x)) for x in v])
                else:
                    params[k] = shlex.quote(str(v))

            self._cmd = cmd.format(**params)
            args = shlex.split(self._cmd)
            decorated_args = f" {fg.magenta(args[0])} {shlex.join(args[1:])}"
            log.info(fg.blue("[sh]") + decorated_args)

            if self._interactive:
                if self._user_input:
                    raise ValueError("Interactive shell can't provide input programmatically.")
                self._sink = EmptyOutputSink()
                self._returncode = subprocess.call(
                    self._cmd,
                    env=digest_env(params),
                    cwd=self._cwd,
                    shell=True)

            else:
                proc = await asyncio.create_subprocess_shell(
                    self._cmd,
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=digest_env(params),
                    cwd=self._cwd
                )

                collector = ShellOutputCollector(proc)
                self._sink = await collector.collect()
                await proc.wait()
                self._returncode = proc.returncode

            self.finish()
            if self.succeeded():
                log.info(fg.green('[ok]') + decorated_args)
                if self.config.verbose:
                    self.report().log_output()
            else:
                log.info(fg.white(bg.red('[!!]')) + decorated_args)
                self.report().log_output()

        finally:
            self._limiter.release()

    def input(self) -> Any:
        return self._input

    def output(self) -> Any:
        return self._output

    def report(self) -> SubprocessReport:
        return SubprocessReport(
            name=self._name,
            started=self.started,
            finished=self.finished,
            cmd=self._cmd,
            sink=self._sink,
            returncode=self._returncode,
        )


# -------------------------------------------------------------------
class ShellRecipeFactory:
    def __init__(self):
        self._env = {**os.environ}

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
