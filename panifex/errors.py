# --------------------------------------------------------------------
# errors.py: Exceptions and error management tools.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------


# --------------------------------------------------------------------
class BuildError(Exception):
    pass

# --------------------------------------------------------------------
class InvalidTargetError(Exception):
    def __init__(self, name):
        self.name = name
        super().__init__("'%s' is not a valid target: %s", name)
