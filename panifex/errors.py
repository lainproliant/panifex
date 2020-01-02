# --------------------------------------------------------------------
# errors.py: Exceptions and error management tools.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
from typing import List


# --------------------------------------------------------------------
class BuildError(Exception):
    pass


# --------------------------------------------------------------------
class SubprocessError(BuildError):
    def __init__(self, cmd: str):
        super().__init__("Failed to execute command: %s" % cmd)


# --------------------------------------------------------------------
class BuildFailure(Exception):
    def __init__(self, target_name: str = None):
        if target_name is None:
            super().__init__("Overall build failed.")
        else:
            super().__init__(f"Failed to build target '{target_name}'.")
        self.target_name = target_name


# --------------------------------------------------------------------
class AggregateError(BuildError):
    def __init__(self, errors: List[Exception]):
        self.errors = errors

    @classmethod
    def aggregate(cls, *values):
        errors = [v for v in values if isinstance(v, Exception)]
        if errors:
            raise AggregateError(errors)
        return values
