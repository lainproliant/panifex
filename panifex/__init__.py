# -------------------------------------------------------------------
# Panifex: The Python dependency-injection based build system.
#
# Author: Lain Musgrove (lainproliant)
# Date: Wednesday, August 12 2020
#
# Released under a 3-clause BSD license, see LICENSE for more info.
# -------------------------------------------------------------------
from .artifacts import Artifact, NullArtifact, PolyArtifact, ValueArtifact
from .files import FileArtifact, FileRecipe, StaticFileRecipe
from .build import BuildEngine, factory, recipe
from .bake import build
from .recipes import PolyRecipe, Recipe, SequenceRecipe
from .shell import check, sh

engine = BuildEngine.default()
provide = engine.provide
target = engine.target

poly = PolyRecipe
seq = SequenceRecipe
