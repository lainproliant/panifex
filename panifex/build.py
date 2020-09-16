# --------------------------------------------------------------------
# build.py: Apply build logic to a Xeno injector.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
import sys
from typing import List

import xeno
from ansilog import fg
from tree_format import format_tree

from .config import Config
from .errors import BuildError
from .recipes import FunctionalRecipe, PolyRecipe, Recipe

# --------------------------------------------------------------------
injector = xeno.AsyncInjector()
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
def provide(f, target=False):
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

    injector.provide(wrapper, is_singleton=True)
    return wrapper


# --------------------------------------------------------------------
def target(f):
    """ A wrapper for `provide`, indicating the resource as a build target. """
    return provide(f, True)


# --------------------------------------------------------------------
def list_targets():
    """ Logs the list of targets currently defined. """
    targets = sorted([k for k, v in injector.scan_resources(lambda k, v: True)])
    values = [injector.require(target) for target in targets]
    recipes = [value for value in values if isinstance(value, Recipe) and value.target]
    for recipe in recipes:
        log.info(recipe.ansi_display_name)


# --------------------------------------------------------------------
def print_tree():
    """ Prints a tree illustrating the dependencies between providers and targets. """
    config = Config.get()

    targets = config.targets

    if not targets:
        targets = [k for k, v in injector.scan_resources(lambda k, v: True)]

    values = [injector.require(target) for target in targets]
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


# --------------------------------------------------------------------
def build(default: str = ""):
    """ This function triggers the build of targets specified.

    If `default` is provided, it will be used as the target if no other targets
    are specified on the command line."""
    config = Config.get()

    if config.print_tree:
        print_tree()
        return

    if config.list_targets:
        list_targets()
        return

    if not config.targets and not default:
        raise BuildError("No target or default specified.")

    targets = config.targets or [default]
    recipes = []
    invalid_targets = False
    for target in targets:
        try:
            try:
                value = injector.require(target.replace("-", "_"))
            except xeno.MissingResourceError:
                raise BuildError("'%s' is not defined." % target)
            if isinstance(value, Recipe) and value.target:
                recipes.append(value)
            else:
                raise BuildError("Target '%s' result is not a Recipe." % target)
        except Exception as e:
            log.error("'%s' is not a valid target: %s", target, e)
            if config.debug:
                log.exception("Exception details >>>")
            invalid_targets = True

    if invalid_targets:
        sys.exit(1)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(resolve(config, recipes))


# --------------------------------------------------------------------
async def resolve(config: Config, recipes: List[Recipe]):
    try:
        if config.clean:
            await asyncio.gather(*[r.clean(True) for r in recipes])
        elif config.purge:
            await asyncio.gather(*[r.purge(True) for r in recipes])
        else:
            await asyncio.gather(*[r.resolve() for r in recipes])
        log.info(fg.green("OK"))

    except Exception as e:
        log.error("An error occurred: %s", e)
        if config.debug:
            log.exception("Exception details >>>")
        log.info(fg.red("FAIL"))
