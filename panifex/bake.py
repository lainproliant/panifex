# --------------------------------------------------------------------
# bake.py: A helper script for running `bake.py` files.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Sunday January 5, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import asyncio
import subprocess
import sys
from ansilog import fg
from pathlib import Path
from typing import Any, Optional

import xeno

from .build import BuildEngine, Goal
from .config import Config
from .errors import BuildError, InvalidTargetError

log = Config.get().get_logger("panifex.bake")


# --------------------------------------------------------------------
def build(default: Any, build: Optional[BuildEngine] = None):
    """ This function triggers the build of targets specified.

    It is intended to be called at the end of `bake.py` build scripts.

    If `default` is provided, it will be used as the target if no other targets
    are specified on the command line."""

    try:
        config = Config.get()
        if build is None:
            build = BuildEngine.default()

        if config.print_tree:
            build.print_tree()
            return

        if config.list_targets:
            build.print_targets()
            return

        if not config.targets and not default:
            raise BuildError("No target or default specified.")

        if callable(default):
            default = xeno.MethodAttributes.for_method(default).get('name')

        recipes = build.compile_targets(config.targets or [default])

        goal = Goal.BUILD
        if config.clean:
            goal = Goal.CLEAN
        elif config.purge:
            goal = Goal.PURGE

        loop = asyncio.get_event_loop()
        loop.run_until_complete(build.resolve(recipes, goal))
        log.info(fg.green("OK"))

    except Exception as e:
        log.error(e)
        if config.debug:
            log.exception("Exception details >>>")
        log.info(fg.red("FAIL"))


# --------------------------------------------------------------------
def main():
    config = Config.get()

    if config.help:
        config.print_help()
        return

    if Path('bake.py').exists():
        subprocess.call(['python', 'bake.py', *sys.argv[1:]])
    else:
        log.error("There is no 'bake.py' in the current directory.")


# --------------------------------------------------------------------
if __name__ == '__main__':
    main()
