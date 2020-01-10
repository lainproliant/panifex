# -------------------------------------------------------------------
# Panifex: The Python dependency-injection based build system.
#
# Author: Lain Musgrove (lainproliant)
# Date: Thursday, January 2 2020
#
# Released under a 3-clause BSD license, see LICENSE for more info.
# -------------------------------------------------------------------

from .build import build, default, seq, keep
from .shell import sh
temp = build.temp
