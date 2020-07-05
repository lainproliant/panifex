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
import tempfile
from typing import Any, Dict, Optional
from datetime import datetime

import ansilog

from .config import DEBUG, REPORT_DATETIME_FORMAT


# --------------------------------------------------------------------
def format_dt(dt: Optional[datetime]):
    return dt.strftime(REPORT_DATETIME_FORMAT) if dt else "Never"


# --------------------------------------------------------------------
def digest_env(env: Dict[str, Any]) -> Dict[str, str]:
    digested: Dict[str, str] = {}
    for k, v in env.items():
        if is_iterable(v):
            env[k] = list(v)
            digested[k] = " ".join(v)
        else:
            digested[k] = str(v)
    return digested


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
def setup_temp_logger():
    tmp = tempfile.NamedTemporaryFile(mode="wt", delete=False)
    tmp.close()
    logger = logging.getLogger("panifex.FileOutputSink")
    logger.propagate = False
    print(f"lmdbg: log filename {tmp.name}")
    handler = logging.FileHandler(tmp.name)
    formatter = logging.Formatter("[%(asctime)s] :: %(message)s")
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger, tmp.name


# --------------------------------------------------------------------
def decode(b: bytes) -> str:
    try:
        return b.decode('utf-8')
    except UnicodeDecodeError:
        return b.decode('ISO-8859-1')
