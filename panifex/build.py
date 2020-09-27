# --------------------------------------------------------------------
# build.py: Apply build logic to a Xeno injector.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
from typing import List, Optional
from enum import Enum

import xeno
from tree_format import format_tree

from .config import Config
from .errors import BuildError, InvalidTargetError
from .recipes import FunctionalRecipe, PolyRecipe, Recipe

# --------------------------------------------------------------------
log = Config.get().get_logger("panifex.build")

# --------------------------------------------------------------------
def factory(f):
    """ A decorator for functions that generate recipies.

    This should be used to decorate functions that return shell recipes using
    `sh` or `ShellFactory`, for example.  The resulting recipe will be named
    after the function used to create it. """

    def wrapper(*args, **kwargs):
        result = f(*args, **kwargs)
        if isinstance(result, Recipe):
            result.name = f.__name__
        return result

    return wrapper


# --------------------------------------------------------------------
def recipe(f):
    """ A decorator for recipes defined by functions.

    See the docs for `panifex.recipe.FunctionalRecipe` for more info. """
    def wrapper(*args, **kwargs):
        recipe = FunctionalRecipe(f, *args, **kwargs)
        recipe.name = f.__name__
        return recipe

    return wrapper


# --------------------------------------------------------------------
class Goal(Enum):
    BUILD = 1
    CLEAN = 2
    PURGE = 3


# --------------------------------------------------------------------
class BuildEngine():
    _default: Optional['BuildEngine'] = None

    def __init__(self):
        self.injector = xeno.AsyncInjector()

    @classmethod
    def default(cls):
        if cls._default is None:
            cls._default = BuildEngine()
        return cls._default

    def provide(self, f, target=False):
        """ A decorator for specifying available resources.

        These resources are then automatically injected into other resource
        providers and targets using a Xeno injector."""

        @xeno.MethodAttributes.wraps(f)
        async def wrapper(*args, **kwargs):
            result = await xeno.async_wrap(f, *args, **kwargs)
            if isinstance(result, Recipe):
                result.name = f.__name__
                result.target = target
            return result

        self.injector.provide(wrapper, is_singleton=True)
        return wrapper

    def target(self, f):
        """ A wrapper for `provide`, indicating the resource as a build target. """
        return self.provide(f, True)

    def print_targets(self):
        """ Logs the list of targets currently defined. """
        targets = sorted([k for k, v in self.injector.scan_resources(lambda k, v: True)])
        values = [self.injector.require(target) for target in targets]
        recipes = [value for value in values if isinstance(value, Recipe) and value.target]
        for recipe in recipes:
            log.info(recipe.ansi_display_name)

    def print_tree(self):
        """ Prints a tree illustrating the dependencies between providers and targets. """
        config = Config.get()

        targets = config.targets

        if not targets:
            targets = [k for k, v in self.injector.scan_resources(lambda k, v: True)]

        values = [self.injector.require(target) for target in targets]
        recipes = [value for value in values if isinstance(value, Recipe)]

        if len(recipes) > 1:
            root = PolyRecipe(recipes)
            root.name = "*"
        elif len(recipes) == 1:
            root = recipes[0]
        else:
            log.error("There are no recipes defined.")
            return

        log.info(
            format_tree(
                root,
                lambda r: r.ansi_display_name_and_input_output,
                lambda r: r.direct_dependencies,
            )
        )

    def compile_targets(self, targets: List[str]):
        recipes = []
        for target in targets:
            try:
                try:
                    value = self.injector.require(target.replace("-", "_"))

                except xeno.MissingResourceError:
                    raise BuildError("'%s' is not defined." % target)

                if isinstance(value, Recipe) and value.target:
                    recipes.append(value)
                else:
                    raise BuildError("Target '%s' result is not a Recipe." % target)

            except Exception as e:
                raise InvalidTargetError(target) from e

        return recipes

    async def resolve(self, recipes: List[Recipe], goal: Goal = Goal.BUILD):
        if goal == Goal.CLEAN:
            await asyncio.gather(*[r.clean(True) for r in recipes])
        elif goal == Goal.PURGE:
            await asyncio.gather(*[r.purge(True) for r in recipes])
        else:
            await asyncio.gather(*[r.resolve() for r in recipes])
