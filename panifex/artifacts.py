# --------------------------------------------------------------------
# artifacts.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Monday August 17, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import asyncio
from typing import (
    Any,
    Generator,
    Generic,
    Iterable,
    List,
    Tuple,
    TypeVar,
)

from datetime import timedelta
from .config import Config
from .util import is_iterable, uniq

# --------------------------------------------------------------------
T = TypeVar("T")

log = Config.get().get_logger("panifex.artifacts")

# --------------------------------------------------------------------
class Artifact:
    """An abstract class representing the output of a recipe, e.g. a
    static file or a resulting system state, which can be used to
    reverse the state or clean the output."""

    async def clean(self):
        """ Delete the output or reverse the state this artifact represents. """
        log.debug(
            "Attempted to clean object of type '%s', which doesn't support cleaning."
            % (type(self))
        )
        raise NotImplementedError()

    @property
    def exists(self) -> bool:
        """ Determine if the output or system state this artifact represents
        actually exists. """
        raise NotImplementedError()

    @property
    def age(self) -> timedelta:
        """ Determine the age of this artifact. """
        return timedelta.max

    @property
    def is_null(self) -> bool:
        """ Returns True if this artifact represents nothing real. """
        return False

    @property
    def value(self) -> Any:
        """ Fetch the underlying value for this artifact. """
        raise NotImplementedError()

    def to_params(self) -> List[Any]:
        """ Convert this artifact's value to a list of interpolatable string
        params for use in commands. """
        return []


# --------------------------------------------------------------------
class ValueArtifact(Artifact, Generic[T]):
    """ Represents a constant value generated by a recipe. """

    def __init__(self, value: T):
        self._value: T = value

    async def clean(self):
        pass

    @property
    def exists(self) -> bool:
        return True

    @property
    def value(self) -> Any:
        return self._value

    def to_params(self) -> List[Any]:
        return [self._value]

    def __hash__(self) -> int:
        return hash(self.value)


# --------------------------------------------------------------------
class NullArtifact(Artifact):
    """ Represents an artifact that doesn't exist. """

    @property
    def exists(self) -> bool:
        return False

    @property
    def is_null(self) -> bool:
        return True

    async def clean(self):
        pass

    def __hash__(self) -> int:
        return 0


# --------------------------------------------------------------------
class PolyArtifact(Artifact):
    """ Represents a compound collection of none or more artifacts. """
    @classmethod
    def _find_leaves(
        cls, artifacts: Iterable[Artifact]
    ) -> Generator[Artifact, None, None]:
        for artifact in artifacts:
            if isinstance(artifact, PolyArtifact):
                yield from cls._find_leaves(artifact._artifacts)
            elif not artifact.is_null:
                yield artifact

    def __init__(self, artifacts: Iterable[Artifact]):
        self._artifacts = tuple(uniq(self._find_leaves(artifacts)))

    async def clean(self):
        await asyncio.gather(*(a.clean() for a in self._artifacts))

    @property
    def exists(self) -> bool:
        return all(a.exists for a in self._artifacts)

    @property
    def age(self) -> timedelta:
        return min(a.age for a in self._artifacts) if self._artifacts else timedelta.max

    @property
    def value(self) -> Any:
        values = []
        for artifact in self._artifacts:
            if is_iterable(artifact.value):
                values.extend([*artifact.value])
            elif not artifact.is_null:
                values.append(artifact.value)
        return values

    def __iter__(self):
        return iter(self._artifacts)

    def __repr__(self):
        sep = ", "
        if not self._artifacts:
            return "<PolyArtifact of (nothing)"
        return f"<PolyArtifact of {sep.join(repr(a) for a in self._artifacts)}>"

    def to_params(self) -> List[Any]:
        params: List[str] = []
        for artifact in self._artifacts:
            params.extend(artifact.to_params())
        return params

    @property
    def leaves(self) -> Tuple[Artifact, ...]:
        return self._artifacts

    def __hash__(self) -> int:
        return hash(self._artifacts)

    @property
    def is_null(self) -> bool:
        return not any(not a.is_null for a in self._artifacts)
