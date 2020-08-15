# --------------------------------------------------------------------
# util.py: Common utility functions.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import inspect
import logging
from typing import Any

import ansilog

from .config import DEBUG


# --------------------------------------------------------------------
def get_logger(name: str) -> logging.Logger:
    logger = ansilog.getLogger(name)
    if DEBUG:
        ansilog.handler.setLevel(logging.DEBUG)
        logger.setLevel(logging.DEBUG)
    return logger


# --------------------------------------------------------------------
def is_iterable(x: Any) -> bool:
    return isinstance(x, (list, tuple, range)) or inspect.isgenerator(x)


# --------------------------------------------------------------------
def decode(b: bytes) -> str:
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('ISO-8859-1')
