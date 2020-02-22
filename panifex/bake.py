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


# --------------------------------------------------------------------
def main():
    subprocess.call(['python', 'bake.py', *sys.argv[1:]])


# --------------------------------------------------------------------
if __name__ == '__main__':
    main()
