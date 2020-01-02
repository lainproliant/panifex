# --------------------------------------------------------------------
# recipe.py: Recipe base classes and utilities.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
import shutil
from datetime import datetime
from pathlib import Path
from typing import Any, List, Optional

import xeno
from ansilog import bg, fg

from .errors import BuildError
from .reports import BuildReport, Report
from .util import get_logger, is_iterable

# -------------------------------------------------------------------
log = get_logger("panifex")


# -------------------------------------------------------------------
class Recipe:
    cleaning = False
    config = None

    def __init__(self):
        self.created = datetime.now()
        self.started: Optional[datetime] = None
        self.finished: Optional[datetime] = None
        self.skipped = False
        RecipeHistory.add(self)

    async def make(self) -> Any:
        self.started = datetime.now()

        if self.cleaning and self.is_done():
            await self._clean()
        elif not self.is_done():
            await self._resolve()
        else:
            self.skipped = True

        self.finished = datetime.now()
        if not self.succeeded():
            raise BuildError("A recipe failed.")

        return self.output()

    def input(self) -> Any:
        raise NotImplementedError()

    def output(self) -> Any:
        raise NotImplementedError()

    async def _resolve(self) -> Any:
        raise NotImplementedError()

    async def _clean(self) -> None:
        raise NotImplementedError()

    async def clean(self) -> None:
        return await self._clean()

    def is_done(self) -> bool:
        return self.finished is not None

    def succeeded(self) -> bool:
        return self.is_done() or self.cleaning

    def failed(self) -> bool:
        return not self.succeeded()

    async def _deep_output(self, value) -> Any:
        if asyncio.iscoroutine(value):
            value = self._deep_output(await value)
        elif isinstance(value, Recipe):
            value = self._deep_output(await value.output())
        elif is_iterable(value):
            value = [self._deep_output(v) for v in value]
        return value

    def report(self) -> Report:
        raise NotImplementedError()


# -------------------------------------------------------------------
class RecipeHistory:
    _history: List[Recipe] = []
    _started: Optional[datetime] = None
    _finished: Optional[datetime] = None

    @classmethod
    def add(cls, recipe: Recipe):
        if cls._started is None:
            cls._started = datetime.now()
        cls._history.append(recipe)

    @classmethod
    def get(cls):
        return list(cls._history)

    @classmethod
    def report(cls, name="Build Report"):
        if not cls._finished:
            cls._finished = datetime.now()
        return BuildReport(name=name, started=cls._started, finished=cls._finished,
                           job_reports=[j.report() for j in cls._history])

    @classmethod
    def clear(cls):
        cls._history = []
        cls._started = None
        cls._finished = None


# -------------------------------------------------------------------
class FileRecipe(Recipe):
    async def _clean(self, value=xeno.NOTHING) -> None:
        if value is xeno.NOTHING:
            await self._clean(self.output())

        elif is_iterable(value):
            await asyncio.gather(*[self._clean(v) for v in value])

        elif value is not None:
            file = Path(value)
            if file.exists():
                log.info(fg.blue('[--]') + ' ' + str(file))
                if file.is_file():
                    file.unlink()
                elif file.is_dir():
                    shutil.rmtree(file)

    def _get_input_mtime(self, value=xeno.NOTHING):
        if value is xeno.NOTHING:
            return self._get_input_mtime(self.input())
        if isinstance(value, str):
            return self._get_input_mtime(Path(value))
        if isinstance(value, Path):
            return value.stat().st_mtime if value.exists() else 0
        if is_iterable(value):
            return max(self._get_input_mtime(x) for x in value)
        return 0

    def is_done(self, value=xeno.NOTHING) -> bool:
        if value is xeno.NOTHING:
            return self.is_done(self.output())
        if is_iterable(value):
            return all(self.is_done(v) for v in value)
        if value is not None:
            output_file = Path(value)
            if not output_file.exists():
                return self.cleaning
            return self._get_input_mtime() < output_file.stat().st_mtime
        return False
