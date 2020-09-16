# -------------------------------------------------------------------
# Panifex: The Python dependency-injection based build system.
#
# Author: Lain Musgrove (lainproliant)
# Date: Wednesday, August 12 2020
#
# Released under a 3-clause BSD license, see LICENSE for more info.
# -------------------------------------------------------------------
from .artifacts import (Artifact, FileArtifact, NullArtifact, PolyArtifact,
                        ValueArtifact)
from .build import build, factory, provide, recipe, target
from .recipes import (FileRecipe, PolyRecipe, Recipe, SequenceRecipe,
                      StaticFileRecipe)
from .shell import check, sh

poly = PolyRecipe
seq = SequenceRecipe
