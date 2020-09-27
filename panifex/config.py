# --------------------------------------------------------------------
# config.py: Panifex configuration options.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import argparse
import logging
import multiprocessing
import os

import ansilog

# --------------------------------------------------------------------
HELP = """
# Panifex: A make-like DI-based Python build system.
## Usage: `bake [OPTION]... [TARGET]...`
Perform a build operation based on the targets defined in `bake.py`.

# Usage Syntax
### Modes
By default, the specified or default targets will be built, unless one of the
options below is specified.

- `-l, --list`: List available build targets.
- `--tree`: Print a tree illustrating the dependencies of the given
  (or default) target.

## Options
- `-c, --clean`: Clean the outputs of the given (or default) target and all
  dependent resources and targets.
- `-x, --clean-target`: Clean the outputs only of the given target.
- `-v, --verbose`: Print extra information at run time.
- `-q, --quiet`: Print nothing during builds, unless something goes wrong.
- `-m, -max`: Specifies the maximum number of simultaneously running sub shells.
  Defaults to the number of CPU cores on the system ({config.cpu_cores}).
- `-D, --debug`: Causes panifex to print copious amounts of diagnostic info,
  including stack traces for runtime exceptions and build errors.
  Can also be enabled by setting the `PANIFEX_DEBUG` environment variable.

## More Info
See @https://github.com/lainproliant/panifex for more info about how to write
panifex `bake.py` build definitions.
""".strip()

# --------------------------------------------------------------------
class Config:
    """ Defines the command line parameters and other configuration options."""

    _instance = None

    def __init__(self):
        self.targets = []
        self.clean = False
        self.purge = False
        self.help = False
        self.verbose = False
        self.quiet = False
        self.print_tree = False
        self.list_targets = False
        self.debug = "PANIFEX_DEBUG" in os.environ
        self.cpu_cores = multiprocessing.cpu_count()
        self.max_shells = self.cpu_cores

    def print_help(self):
        self.get_logger("panifex.config").info(HELP.format(config=self))

    def get_logger(self, name: str) -> logging.Logger:
        logger = ansilog.getLogger(name)
        if self.debug:
            ansilog.handler.setLevel(logging.DEBUG)
            logger.setLevel(logging.DEBUG)
        else:
            ansilog.handler.setLevel(logging.INFO)
            logger.setLevel(logging.INFO)
        return logger

    @classmethod
    def get_parser(cls, desc) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(description=desc, add_help=False)
        parser.add_argument("targets", nargs="*", default=None)
        parser.add_argument("--help", "-h", dest="help", action="store_true")
        parser.add_argument("--clean", "-c", dest="purge", action="store_true")
        parser.add_argument("--purge", "-x", dest="clean", action="store_true")
        parser.add_argument("--verbose", "-v", dest="verbose", action="store_true")
        parser.add_argument("--quiet", "-q", dest="quiet", action="store_true")
        parser.add_argument("--tree", dest="print_tree", action="store_true")
        parser.add_argument("--list", "-l", dest="list_targets", action="store_true")
        parser.add_argument("--debug", "-D", dest="debug", action="store_true")
        parser.add_argument("--max", "-m", dest="max_shells", type=int)
        return parser

    @classmethod
    def get(cls) -> "Config":
        if cls._instance is None:
            cls._instance = Config().load()
        return cls._instance

    def load(self, desc="Build parameters") -> "Config":
        parser = self.get_parser(desc)
        parser.parse_args(namespace=self)
        return self
