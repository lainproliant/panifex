# --------------------------------------------------------------------
# build.py: The main BuildEngine definition.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import asyncio
import inspect
import json
import sys
from typing import Any, List
from ansilog import fg, bg

import xeno

from .config import Config
from .errors import BuildError, AggregateError
from .recipes import Recipe, RecipeHistory
from .util import get_logger, is_iterable

# --------------------------------------------------------------------
DEFAULT_TARGET = "panifex.default_target"
KEEP = "panifex.keep"


# --------------------------------------------------------------------
log = get_logger("panifex")


# -------------------------------------------------------------------
def default(f):
    attrs = xeno.MethodAttributes.for_method(f, create=True, write=True)
    attrs.put(DEFAULT_TARGET)
    return f


# -------------------------------------------------------------------
def keep(f):
    attrs = xeno.MethodAttributes.for_method(f, create=True, write=True)
    attrs.put(KEEP)
    return f


# -------------------------------------------------------------------
class Sequential:
    def __init__(self, *items):
        self.items = items


# -------------------------------------------------------------------
@xeno.namespace("build")
class BuildEngine:
    name = "Build script."

    def __init__(self, exit_on_error=True):
        self._exit_on_error = exit_on_error
        self._initialize()

    def _initialize(self):
        Recipe.cleaning = False
        self._injector = xeno.Injector()
        self._cache = {}
        self._temps = []

    def temp(self, f):
        @xeno.MethodAttributes.wraps(f)
        async def wrapper(*args, **kwargs):
            result = await xeno.async_wrap(f, *args, **kwargs)
            if is_iterable(result):
                self._temps.extend(result)
            else:
                self._temps.append(result)
            return result

        return wrapper

    # pylint: disable=R0201
    def noclean(self, f):
        async def wrapper(*args, **kwargs):
            if Recipe.cleaning:
                return None
            return await xeno.async_wrap(f, *args, **kwargs)

        return wrapper

    @xeno.provide
    def log(self):
        return log

    def build_report(self, filename=None):
        pass

    def __call__(self, *module_objects):
        config = Recipe.config = Config().parse_args(self.name)

        try:
            if len(module_objects) > 1:
                def impl(module):
                    modules = [
                        obj() if inspect.isclass(obj) else obj for obj in module_objects
                    ]
                    return self._resolve_build(modules, config)
                return impl

            module = module_objects[0]
            module = module() if inspect.isclass(module) else module
            result = self._resolve_build([module], config)
            log.info("")
            if Recipe.cleaning:
                log.info(fg.green("CLEAN"))
            else:
                log.info(fg.green("OK"))
            return result

        except AggregateError as e:
            if config.verbose:
                log.exception("Aggregate exception details >>>")
                for err in e.errors:
                    log.info("")
                    for err in e.errors:
                        log.exception("Sub-exception >>>", exc_info=err)
                else:
                    for err in e.errors:
                        log.error(f"{type(err).__name__}: {err}")

            log.info("")
            log.info(fg.white(bg.red("FAIL")))
            if self._exit_on_error:
                sys.exit(1)

        except Exception as e:
            if config.verbose:
                log.exception("Fatal exception details >>>")
            else:
                log.error(f"{type(e).__name__}: {e}")

            log.info("")
            log.info(fg.white(bg.red("FAIL")))
            if self._exit_on_error:
                sys.exit(1)

        finally:
            RecipeHistory.clear()
            Recipe.config = Config()
            self._initialize()

    def _resolve_build(self, modules: List[Any], config: Config):
        if not modules:
            raise BuildError("At least one build class or object must be provided.")

        Recipe.cleaning = config.cleaning or config.clean_all

        main_module, *support_modules = modules
        default_target, defined_targets = self._patch_module(main_module, main_module=True)
        for module in support_modules:
            self._patch_module(module)
        self._injector.add_async_injection_interceptor(self._intercept_coroutines)
        self._injector.add_module(main_module, skip_cycle_check=True)
        for module in support_modules:
            self._injector.add_module(module, skip_cycle_check=True)
        self._injector.check_for_cycles()

        keepers = self._get_keepers()

        if not config.target:
            if default_target:
                config.target = default_target
            else:
                raise BuildError('No target was specified and no default target is defined.')

        if config.clean_all:
            targets = defined_targets
        elif not Recipe.cleaning:
            targets = [*self._injector.get_ordered_dependencies(config.target), config.target]
        else:
            targets = [config.target]

        if Recipe.cleaning:
            targets = [t for t in targets if t not in keepers or t == config.target]

        for target in targets:
            if target not in defined_targets:
                raise BuildError(f'Unknown target: "{target}".')

        loop = asyncio.get_event_loop()
        result_map = {
            target: loop.run_until_complete(self._resolve_resource(target, targeted=True))
            for target in targets
        }
        loop.run_until_complete(self._cleanup_temps())

        return result_map

    def _patch_module(self, module, main_module=False):
        """Patch the modules so that all methods not starting with underscore
        are modded to be Xeno providers."""
        default_target = None
        targets = []
        cls = type(module)
        for name, method in inspect.getmembers(cls, predicate=inspect.isfunction):
            if not name.startswith("_"):
                setattr(cls, name, xeno.singleton(method))
                attrs = xeno.MethodAttributes.for_method(method)
                name = attrs.get("name")
                targets.append(name)
                if main_module and attrs.check(DEFAULT_TARGET):
                    default_target = name
        return default_target, targets

    def _get_keepers(self):
        """Get all resources tagged as 'keepers', these will only be cleaned when
        explicitly specified as targets."""
        return {k for k, v in self._injector.scan_resources(lambda key, att: att.check(KEEP))}

    async def _resolve_resource(self, name, value=xeno.NOTHING, alias=None, targeted=False):
        name = alias or name
        if name in self._cache and not Recipe.cleaning:
            value = self._cache[name]

        else:
            value = (
                await self._injector.require_async(name)
                if value is xeno.NOTHING
                else value
            )

            try:
                if not Recipe.cleaning or targeted:
                    log.info(fg.blue('[..]') + ' ' + name)
                value = self._cache[name] = await self._deep_resolve(value, targeted)
                if not Recipe.cleaning:
                    log.info(fg.green('[ok]') + ' ' + name)

            except Exception as e:
                log.info(fg.white(bg.red('[!!]')) + ' ' + name)
                raise e

        return value

    async def _deep_resolve(self, value, targeted=False):
        if isinstance(value, Recipe):
            return await self._deep_resolve(await value.make(targeted))
        if inspect.isgenerator(value):
            return await self._deep_resolve(list(value), targeted=targeted)
        if asyncio.iscoroutine(value):
            return await self._deep_resolve(await value)
        if isinstance(value, Sequential):
            return [await self._deep_resolve(v, targeted=targeted) for v in value.items]
        if is_iterable(value):
            return AggregateError.aggregate(
                *await asyncio.gather(
                    *(self._deep_resolve(v, targeted=targeted) for v in value), return_exceptions=True
                )
            )
        return value

    async def _intercept_coroutines(self, attrs, param_map, alias_map):
        return {
            k: await self._resolve_resource(k, value=v, alias=alias_map[k])
            for k, v in param_map.items()
        }

    async def _cleanup_temps(self):
        result = AggregateError.aggregate(await asyncio.gather(
            *[x.clean() for x in self._temps], return_exceptions=True
        ))
        return result


# -------------------------------------------------------------------
build = BuildEngine()
seq = Sequential
