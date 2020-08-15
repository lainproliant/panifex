# --------------------------------------------------------------------
# config.py: Panifex configuration options.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import os
import multiprocessing

# --------------------------------------------------------------------
CPU_CORES = multiprocessing.cpu_count()
DEBUG = "PANIFEX_DEBUG" in os.environ
