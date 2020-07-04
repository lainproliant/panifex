# --------------------------------------------------------------------
# test-sudo-outsider.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday July 4 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

from panifex import build, default, sh


# --------------------------------------------------------------------
@default
def yay_upgrade():
    return sh("yay -Syu").interactive()


# --------------------------------------------------------------------
build()
