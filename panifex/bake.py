# --------------------------------------------------------------------
# bake.py: A helper script for running `bake.py` files.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Sunday January 5, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import subprocess
import sys
from pathlib import Path

from .config import Config

log = Config.get().get_logger("panifex.bake")

# --------------------------------------------------------------------
def main():
    config = Config.get()

    if config.help:
        config.print_help()
        return

    if Path('bake.py').exists():
        subprocess.call(['python', 'bake.py', *sys.argv[1:]])
    else:
        log.error("There is no 'bake.py' in the current directory.")


# --------------------------------------------------------------------
if __name__ == '__main__':
    main()
