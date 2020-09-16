# --------------------------------------------------------------------
# recipe.py: Recipe base classes and utilities.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
from enum import Enum
from pathlib import Path
from typing import Any, Dict, Generator, Iterable, List, Optional, Set, Union

import xeno
from ansilog import dim, fg
from tree_format import format_tree

from .artifacts import (Artifact, FileArtifact, NullArtifact, PolyArtifact,
                        ValueArtifact, digest_param)
from .config import Config
from .errors import BuildError
from .util import badge

# --------------------------------------------------------------------
log = Config.get().get_logger("panifex.recipe")

# --------------------------------------------------------------------
def if_not_quiet(f):
    def wrapper(*args, **kwargs):
        config = Config.get()
        if not config.quiet:
            f(*args, **kwargs)
    return wrapper


# --------------------------------------------------------------------
class Recipe:
    """ Represents a repeatable process. """

    def __init__(self, input: Optional[List["Recipe"]] = None):
        self._deps: List["Recipe"] = input or []
        self.name: Optional[str] = None
        self.target = False
        self._lock = asyncio.Lock()

    @property
    def display_name(self) -> str:
        return self.name or self.__class__.__name__

    @property
    def display_info(self) -> Optional[str]:
        return None

    @property
    def ansi_display_info(self) -> Optional[str]:
        return self.display_info

    @property
    def ansi_display_name(self) -> str:
        color = fg.cyan if self.target else dim
        return str(color(self.display_name))

    @property
    def ansi_display_name_and_input_output(self) -> str:
        input_display: Optional[str] = None
        output_display: Optional[str] = None
        if not self.input.is_null:
            input_display = f"{fg.blue(', '.join(digest_param(self.input, Path.cwd())))}"
        if not self.output.is_null:
            output_display = f"{fg.green(', '.join(digest_param(self.output, Path.cwd())))}"

        if input_display and output_display:
            return f"{badge(self.ansi_display_name)} {input_display} -> {output_display}"
        if input_display:
            return f"{badge(self.ansi_display_name)} {input_display}"
        if output_display:
            return f"{badge(self.ansi_display_name)} -> {output_display}"
        return f"{badge(self.ansi_display_name)}"

    @if_not_quiet
    def log_start(self):
        if self.target:
            log.info(f"{badge(self.ansi_display_name)} start")

    @if_not_quiet
    def log_action(self):
        if self.ansi_display_info:
            log.info(f"{badge(self.ansi_display_name)} {self.ansi_display_info}")

    @if_not_quiet
    def log_cleaning(self):
        log.info(f"{badge(fg.yellow(self.display_name))} cleaning")

    @if_not_quiet
    def log_cleaned(self):
        log.info(f"{badge(fg.yellow(self.display_name))} clean ok")

    @if_not_quiet
    def log_purging(self):
        log.info(f"{badge(fg.yellow(self.display_name))} purging")

    @if_not_quiet
    def log_purged(self):
        log.info(f"{badge(fg.yellow(self.display_name))} purge ok")

    @if_not_quiet
    def log_ok(self):
        if self.target:
            log.info(f"{badge(fg.green(self.display_name))} ok")

    def log_exception(self, e: Exception, exc_info=False):
        log.exception(f"{badge(fg.red(self.display_name))} {str(e)}", exc_info=exc_info)

    @property
    def is_done(self) -> bool:
        """ Determine if all of the artifacts of this recipe exist and
        are up to date.  Will always return false if there are no artifacts
        made by this recipe. """
        log.debug("self.name: %s" % self.name)
        log.debug("self.output: %s" % str(self.output))
        log.debug("self.output.exists: %s" % str(self.output.exists))
        log.debug("self.input.age: %s", str(self.input.age))
        log.debug("self.output.age: %s", str(self.output.age))
        log.debug("self.output.age <= self.input.age: %s", str(self.output.age <= self.input.age))
        log.debug("is_done: %s" % str(self.output.exists and self.output.age <= self.input.age))
        return self.output.exists and self.output.age <= self.input.age

    def assert_is_done(self):
        if not self.is_done:
            raise BuildError("Recipe did not complete successfully.")

    async def make(self):
        """ Execute this recipe in order to create its artifacts, if any. """
        raise NotImplementedError()

    def make_sync(self, loop=asyncio.get_event_loop()):
        """ Execute this recipe in order to create its artifacts, if any.
        Can be called outside but not within an event loop. """
        loop.run_until_complete(self.make())

    async def resolve_deps(self):
        """ Make all dependencies of this recipe. """
        await asyncio.gather(
            *(recipe.resolve() for recipe in self.direct_dependencies if not recipe.is_done)
        )
        for recipe in self.dependencies:
            recipe.assert_is_done()

    def resolve_deps_sync(self, loop=asyncio.get_event_loop()):
        """ Make all dependencies of this recipe.
        Can be called outside but not within an event loop. """
        loop.run_until_complete(self.resolve_deps())

    async def resolve(self):
        """ Execute this recipe and all its dependencies, if any. """
        config = Config.get()
        async with self._lock:
            if not self.is_done:
                try:
                    self.log_start()
                    await self.resolve_deps()
                    self.log_action()
                    await self.make()
                    self.assert_is_done()
                    self.log_ok()

                except Exception as e:
                    self.log_exception(e)
                    if config.debug:
                        raise e

    def resolve_sync(self, loop=asyncio.get_event_loop()):
        """ Execute this recipe and all of its dependencies, if any.
        Can be called outside but not within an event loop. """
        loop.run_until_complete(self.resolve())

    async def clean(self, echo=False):
        """ Clean all of the artifacts this recipe would make, if any. """
        if self.output.exists:
            if echo:
                self.log_cleaning()
            await self.output.clean()
            if echo:
                self.log_cleaned()

    def clean_sync(self, loop=asyncio.get_event_loop()):
        """ Clean all of the artifacts this recipe would make, if any.
        Can be called outside but not within an event loop. """
        loop.run_until_complete(self.clean())

    async def purge(self, echo=False):
        """ Clean this and all dependencies. """
        if self.output.exists or any(dep.output.exists for dep in self.dependencies):
            if echo:
                self.log_purging()
            await asyncio.gather(*(dep.purge() for dep in self.dependencies))
            await self.clean()
            if echo:
                self.log_purged()

    def purge_sync(self, loop=asyncio.get_event_loop()):
        """ Clean this and all dependencies.
        Can be called outside but not within an event loop. """
        loop.run_until_complete(self.purge())

    def print_tree(self):
        log.info(
            format_tree(
                self,
                format_node=lambda x: x.ansi_display_name_and_input_output,
                get_children=lambda x: x.direct_dependencies,
            )
        )

    @property
    def output(self) -> Artifact:
        """ List of the artifacts made by this recipe.  This should reflect the
        reversible system states changed by executing this recipe. """
        return NullArtifact()

    @property
    def input(self) -> Artifact:
        """ The artifact or artifacts that this recipe uses.  Defined by the
        artifacts generated by its dependencies. """
        return PolyRecipe(self.dependencies).output

    @property
    def dependencies(self) -> List["Recipe"]:
        """ List of the recipes that must be completed before this recipe can
        be executed. """
        return self._deps

    @property
    def direct_dependencies(self) -> List["Recipe"]:
        """ List of the direct dependencies, i.e. the last recipes that need to
        be completed before this recipe can be executed. """
        return sorted(self._deps, key=lambda x: x.name or x.__class__.__name__)

    def __repr__(self):
        return f"<{self.__class__.__name__} for " f"{self.output}>"


# --------------------------------------------------------------------
class ParamType(Enum):
    POSITIONAL = "Positional"
    KEYWORD = "Keyword"


# --------------------------------------------------------------------
class LazyRecipeParam:
    def __init__(self, type: ParamType, position: Union[str, int], recipe: Recipe):
        self.type = type
        self.position = position
        self.recipe = recipe

    def interpolate(self, args: List[Any], kwargs: Dict[str, Any]):
        if self.type == ParamType.POSITIONAL and isinstance(self.position, int):
            args[self.position] = self.recipe.output.value
        elif self.type == ParamType.KEYWORD and isinstance(self.position, str):
            kwargs[self.position] = self.recipe.output.value
        else:
            raise ValueError("Invalid type/value type combination.")


# --------------------------------------------------------------------
class FunctionalRecipe(Recipe):
    def __init__(self, f, *args, **kwargs):
        self._lazy_params: List[LazyRecipeParam] = []
        self._f = f
        self.args = [*args]
        self.kwargs = {**kwargs}
        self.result = None
        self.done = False
        super().__init__(self._scan_args())

    def _scan_args(self) -> List[Recipe]:
        recipes = []
        for x, arg in enumerate(self.args):
            if isinstance(arg, Recipe):
                self._lazy_params.append(LazyRecipeParam(ParamType.POSITIONAL, x, arg))
                recipes.append(arg)

        for key, value in self.kwargs.items():
            if isinstance(value, Recipe):
                self._lazy_params.append(LazyRecipeParam(ParamType.KEYWORD, key, value))
                recipes.append(arg)

        return recipes

    @property
    def is_done(self) -> bool:
        return self.done

    @property
    def output(self) -> Artifact:
        if self.done:
            return ValueArtifact(self.result)
        return NullArtifact()

    async def make(self):
        try:
            for param in self._lazy_params:
                param.interpolate(self.args, self.kwargs)
            self.result = await xeno.async_wrap(self._f, *self.args, **self.kwargs)
            self.done = True

        except Exception as e:
            self.done = False
            raise e


# --------------------------------------------------------------------
class PolyRecipe(Recipe):
    @classmethod
    def _calculate_deps(cls, recipes: List[Recipe]) -> List[Recipe]:
        deps_set: Set[Recipe] = set(recipes)
        for recipe in recipes:
            deps_set.update(recipe.dependencies)
        return list(deps_set)

    def __init__(self, recipes: Iterable[Recipe]):
        self._recipes = list(recipes)
        super().__init__(self._calculate_deps(self._recipes))

    @property
    def is_done(self) -> bool:
        return all(r.is_done for r in self._recipes)

    @property
    def direct_dependencies(self):
        return sorted(self._recipes, key=lambda x: x.name or x.__class__.__name__)

    @property
    def input(self) -> Artifact:
        return NullArtifact()

    @property
    def output(self) -> Artifact:
        return PolyArtifact(set(self._find_output()))

    def _find_output(self) -> Generator[Artifact, None, None]:
        for recipe in self._recipes:
            if isinstance(recipe, PolyRecipe):
                yield from recipe._find_output()
            elif not recipe.output.is_null:
                yield recipe.output

    async def make(self):
        await asyncio.gather(*(recipe.resolve() for recipe in self._recipes))

    def __iter__(self):
        return iter(self._recipes)


# --------------------------------------------------------------------
class SequenceRecipe(PolyRecipe):
    def __init__(self, recipes: Iterable[Recipe]):
        super().__init__(recipes)

    async def make(self):
        for recipe in self._recipes:
            await recipe.resolve()


# --------------------------------------------------------------------
class FileRecipe(Recipe):
    """ A recipe for creating a single file or directory. """

    def __init__(self, path: Path, input: Optional[List[Recipe]] = None):
        super().__init__(input)
        self.path = path

    @property
    def output(self) -> Artifact:
        return FileArtifact(self.path)


# --------------------------------------------------------------------
class StaticFileRecipe(FileRecipe):
    """ A recipe for static files that must exist. """

    def __init__(self, path: Path):
        super().__init__(path)

    async def make(self):
        raise BuildError(f"A required static file is missing: {self.path}")
