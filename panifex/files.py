# --------------------------------------------------------------------
# files.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Saturday September 26, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import shutil
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional, Tuple, TypeVar

from ansilog import dim

from .artifacts import Artifact, NullArtifact, ValueArtifact
from .config import Config
from .errors import BuildError
from .params import digest_param
from .recipes import Recipe
from .util import badge

# --------------------------------------------------------------------
T = TypeVar("T")
log = Config.get().get_logger("panifex.files")

# --------------------------------------------------------------------
class FileArtifact(Artifact):
    """ Represents a file or directory output from a recipe. """

    def __init__(self, path: Path):
        self.path = path

    @property
    def exists(self) -> bool:
        return self.path.exists()

    @property
    def age(self) -> timedelta:
        if not self.exists:
            return timedelta.max
        return datetime.now() - datetime.fromtimestamp(self.path.stat().st_mtime)

    @property
    def value(self) -> Any:
        return self.path

    async def clean(self):
        if self.exists:
            log.info(
                f"{badge(dim('delete'))} {dim(digest_param(self.path, Path.cwd())[0])}"
            )
            if self.path.is_dir():
                shutil.rmtree(self.path)
            else:
                self.path.unlink()

    def __repr__(self):
        return f"<FileArtifact {str(self.path)}>"

    def __str__(self):
        return str(self.path)

    def to_params(self) -> List[Any]:
        return [self.path]

    def __hash__(self) -> int:
        return hash(self.path)


# --------------------------------------------------------------------
class FileRecipe(Recipe):
    """ A recipe for creating a single file or directory. """

    def __init__(self, path: Path, input: Optional[List[Recipe]] = None):
        super().__init__(input)
        self.path = path

    @property
    def output(self) -> Artifact:
        return FileArtifact(self.path)


# --------------------------------------------------------------------
class StaticFileRecipe(FileRecipe):
    """ A recipe for static files that must exist. """

    def __init__(self, path: Path):
        super().__init__(path)

    async def make(self):
        raise BuildError(f"A required static file is missing: {self.path}")


# --------------------------------------------------------------------
def as_artifact(obj: T, str_as_file=False) -> Artifact:
    """Interpret the given parameter as an artifact.  If str_as_file is True,
    any string values will be interpreted as relative paths to files and
    generate FileArtifacts."""

    if obj is None:
        return NullArtifact()
    if isinstance(obj, Artifact):
        return obj
    if isinstance(obj, Path):
        return FileArtifact(obj)
    if isinstance(obj, str) and str_as_file:
        return FileArtifact(Path(obj))
    return ValueArtifact(obj)


# --------------------------------------------------------------------
def categorize_params(
    params: List[Any], str_as_file=False
) -> Tuple[List[Artifact], List[Recipe]]:
    pass
