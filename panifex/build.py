# --------------------------------------------------------------------
# build.py: Apply build logic to a Xeno injector.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Wednesday, August 12 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import argparse
import xeno
from .recipes import Recipe
from .errors import BuildError


# --------------------------------------------------------------------
class Config:
    def __init__(self):
        self.targets = []
        self.clean = False
        self.purge = False
        self.verbose = False

    @classmethod
    def get_parser(cls, desc):
        parser = argparse.ArgumentParser(description=desc)
        parser.add_argument("targets", nargs="?", default=None)
        parser.add_argument("--clean", "-c", dest="clean", action="store_true")
        parser.add_argument("--purge", "-X", dest="purge", action="store_true")
        parser.add_argument("--verbose", "-v", dest="verbose", action="store_true")
        return parser

    def parse_args(self, desc="Build parameters"):
        parser = self.get_parser(desc)
        parser.parse_args(namespace=self)
        return self


# --------------------------------------------------------------------
injector = xeno.AsyncInjector()


# --------------------------------------------------------------------
def provide(name_or_method, value=xeno.NOTHING):
    injector.provide(name_or_method, value, is_singleton=True)


# --------------------------------------------------------------------
def build(default: str = ""):
    config = Config().parse_args()

    if not config.targets and not default:
        raise BuildError("No target or default specified.")

    targets = config.targets or [default]
    for target in targets:
        resolve(config, target)


# --------------------------------------------------------------------
def resolve(config: Config, target: str):
    recipe: Recipe = injector.require(target)

    if not isinstance(recipe, Recipe):
        raise BuildError(f'"{target}" is not a recipe.')

    if config.clean:
        recipe.clean_sync()
    elif config.purge:
        recipe.purge_sync()
    else:
        recipe.resolve_sync()
