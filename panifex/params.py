# --------------------------------------------------------------------
# params.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Saturday September 26, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import shlex
from typing import Any, Dict, List, Set, Tuple, Union, Optional
from pathlib import Path

from .util import is_iterable, relative_to
from .artifacts import Artifact
from .recipes import Recipe

EnvironmentValue = Union[str, Set[str], Tuple[str], List[str]]
EnvironmentDict = Dict[str, EnvironmentValue]

# --------------------------------------------------------------------
def digest_env(env: EnvironmentDict) -> Dict[str, str]:
    """Digest the given EnvironmentDict into a flat dictionary by joining any
    iterable values into shell-escaped strings."""
    result = {}

    for key, value in env.items():
        if isinstance(value, (list, set, tuple)):
            result[key] = shlex.join([str(x) for x in value])
        else:
            result[key] = value
    return result


# --------------------------------------------------------------------
def digest_param(value: Any, cwd: Optional[Path] = None) -> List[str]:
    """Digest the given parameter into a list of string values for command
    interpolation."""
    if is_iterable(value):
        result = []
        for p in value:
            result.extend(digest_param(p, cwd))
        return result
    if isinstance(value, Artifact):
        return digest_param(value.to_params(), cwd)
    if isinstance(value, Recipe):
        return digest_param(value.output.to_params(), cwd)
    if cwd is not None and isinstance(value, Path):
        return digest_param(str(relative_to(cwd, value)), cwd)
    return [str(value)]


# --------------------------------------------------------------------
def digest_param_map(
    param_map: Dict[str, Any], cwd: Optional[Path] = None
) -> Dict[str, str]:
    result = {}
    for key, value in param_map.items():
        result[key] = shlex.join(digest_param(value, cwd))
    return result
