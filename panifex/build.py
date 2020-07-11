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
import logging
import sys
from datetime import datetime
from typing import Any, List, Dict

import xeno
from ansilog import bg, fg, Formatter
from collections import defaultdict

from .config import Config
from .errors import AggregateError, BuildError
from .recipes import Recipe, RecipeHistory
from .util import get_logger, is_iterable

# --------------------------------------------------------------------
TARGET = "panifex.target"
DEFAULT_TARGET = "panifex.default_target"
KEEP = "panifex.keep"


# --------------------------------------------------------------------
log = get_logger("panifex")
file_logging_setup = False


# -------------------------------------------------------------------
def _target(f):
    attrs = xeno.MethodAttributes.for_method(f, create=True, write=True)
    attrs.put(TARGET)
    return f


# -------------------------------------------------------------------
def _default(f):
    attrs = xeno.MethodAttributes.for_method(f, create=True, write=True)
    attrs.put(DEFAULT_TARGET)
    return _target(f)


# -------------------------------------------------------------------
def _keep(f):
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
        self._cache_locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._temps = []

    def default(self, f):
        self._injector.provide(_default(f))

    def target(self, f):
        self._injector.provide(_target(f))

    def provide(self, f):
        self._injector.provide(f)

    def temp(self, f):
        @xeno.MethodAttributes.wraps(f)
        async def wrapper(*args, **kwargs):
            result = await xeno.async_wrap(f, *args, **kwargs)
            if is_iterable(result):
                self._temps.extend(result)
            else:
                self._temps.append(result)
            return result
        self.provide(wrapper)
        return wrapper

    def keep(self, f):
        return _keep(f)

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

    def _setup_file_logging(self, config: Config):
        filename = '%s-%s.log' % (config.log_to_file, datetime.today().isoformat())
        file_handler = logging.FileHandler(filename, mode='w')
        file_handler.setFormatter(Formatter(file_handler.stream))
        log.addHandler(file_handler)
        log.info("Logging to file: %s", filename)

    def __call__(self):
        config = Recipe.config = Config().parse_args(self.name)

        if len(config.log_to_file) > 0:
            self._setup_file_logging(config)

        try:
            result = self._resolve_build(config)
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

    def _resolve_build(self, config: Config):
        Recipe.cleaning = config.cleaning or config.clean_all

        self._injector.add_async_injection_interceptor(self._intercept_coroutines)
        self._injector.check_for_cycles()

        keepers = self._get_keepers()

        if not config.target:
            if self._get_default_target():
                config.target = self._get_default_target()
            else:
                raise BuildError('No target was specified and no default target is defined.')

        if config.target not in self._get_targets():
            raise BuildError(f'Unknown target: "{config.target}".')

        if config.clean_all:
            resources = self._get_targets()
        elif not Recipe.cleaning:
            resources = [*self._injector.get_ordered_dependencies(config.target), config.target]
        else:
            resources = [config.target]

        if Recipe.cleaning:
            resources = [t for t in resources if t not in keepers]

        loop = asyncio.get_event_loop()
        result_map = {
            resource: loop.run_until_complete(self._resolve_resource(resource, targeted=True))
            for resource in resources
        }
        loop.run_until_complete(self._cleanup_temps())

        return result_map

    def _get_targets(self):
        """Get all resources tagged as 'targets'."""

        return {k for k, v in self._injector.scan_resources(lambda key, att: att.check(TARGET))}

    def _get_default_target(self):
        """Get the single resource marked as the default target."""
        default_targets = [k for k, v in self._injector.scan_resources(
            lambda key, att: att.check(DEFAULT_TARGET))]
        if len(default_targets) > 1:
            raise BuildError(
                'More than one target is specified as a default target: %s'
                % repr(default_targets))
        return default_targets[0] if default_targets else []

    def _get_keepers(self):
        """Get all resources tagged as 'keepers', these will only be cleaned when
        explicitly specified as targets."""
        return {k for k, v in self._injector.scan_resources(lambda key, att: att.check(KEEP))}

    async def _resolve_resource(self, name, value=xeno.NOTHING, alias=None, targeted=False):
        name = alias or name
        async with self._cache_locks[name]:
            if name in self._cache and not Recipe.cleaning:
                return self._cache[name]

            provided_value = (
                await self._injector.require_async(name)
                if value is xeno.NOTHING
                else value
            )

            try:
                if not Recipe.cleaning or targeted:
                    log.info(fg.blue('[..]') + ' ' + name)
                final_value = self._cache[name] = await self._deep_resolve(provided_value, targeted)
                if not Recipe.cleaning:
                    log.info(fg.green('[ok]') + ' ' + name)

                return final_value

            except Exception as e:
                log.info(fg.white(bg.red('[!!]')) + ' ' + name)
                raise e

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
            k: await self._resolve_resource(k, value=xeno.NOTHING, alias=alias_map[k])
            for k, v in param_map.items()
        }

    async def _cleanup_temps(self):
        result = AggregateError.aggregate(await asyncio.gather(
            *[x.clean() for x in self._temps], return_exceptions=True
        ))
        return result


# -------------------------------------------------------------------
build = BuildEngine()
default = build.default
target = build.target
provide = build.provide
keep = build.keep
seq = Sequential
