# --------------------------------------------------------------------
# test-sudo.py
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday January 30, 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------

import panifex

@panifex.build
class UpgradeYaySudoTest:
    def yay_upgrade(self):
        return panifex.sh("yay -Syu").interactive()
