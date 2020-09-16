# --------------------------------------------------------------------
# util.py: Common utility functions.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import inspect
from pathlib import Path
from typing import Any

# --------------------------------------------------------------------
def relative_to(pivot: Path, path: Path) -> Path:
    try:
        return path.relative_to(pivot)
    except ValueError:
        return path


# --------------------------------------------------------------------
def is_iterable(x: Any) -> bool:
    return isinstance(x, (list, tuple, range)) or inspect.isgenerator(x)


# --------------------------------------------------------------------
def badge(s: str) -> str:
    return "[ %s ]" % s


# --------------------------------------------------------------------
def decode(b: bytes) -> str:
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        return b.decode("ISO-8859-1")
