# -------------------------------------------------------------------
# Panifex: The Python dependency-injection based build system.
#
# Author: Lain Musgrove (lainproliant)
# Date: Wednesday, August 12 2020
#
# Released under a 3-clause BSD license, see LICENSE for more info.
# -------------------------------------------------------------------
from .build import build, provide
from .recipes import (Artifact, File, FileRecipe, PolyRecipe, Recipe,
                      RecipeSequence, StaticFileRecipe, Value)
from .shell import sh, check

poly = PolyRecipe
seq = RecipeSequence
