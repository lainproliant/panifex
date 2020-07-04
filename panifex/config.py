# --------------------------------------------------------------------
# config.py: Panifex configuration options.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import argparse
import os
import multiprocessing


# --------------------------------------------------------------------
CPU_CORES = multiprocessing.cpu_count()
DEBUG = "PANIFEX_DEBUG" in os.environ
FILENAME_DATE_FORMAT = "%Y-%m-%d"
FILENAME_TIME_FORMAT = "%H%M_%S"
FILENAME_DATETIME_FORMAT = f'{FILENAME_DATE_FORMAT}_{FILENAME_TIME_FORMAT}'
REPORT_DATE_FORMAT = "%Y-%m-%d"
REPORT_TIME_FORMAT = "%H:%M:%S"
REPORT_DATETIME_FORMAT = f'{REPORT_DATE_FORMAT} {REPORT_TIME_FORMAT}'


# -------------------------------------------------------------------
class Config:
    def __init__(self):
        self.target = None
        self.cleaning = False
        self.clean_all = False
        self.verbose = False
        self.log_to_file = ""

    @classmethod
    def get_parser(cls, desc):
        parser = argparse.ArgumentParser(description=desc)
        parser.add_argument("target", metavar="target", nargs="?", default=None)
        parser.add_argument("-C", "--clean-target", dest="cleaning", action="store_true")
        parser.add_argument("-c", "--clean", dest="clean_all", action="store_true")
        parser.add_argument('-v', "--verbose", default=False, action="store_true")
        parser.add_argument('-F', "--log-to-file", dest="log_to_file")
        return parser

    def parse_args(self, desc):
        parser = self.get_parser(desc)
        parser.parse_known_args(namespace=self)
        return self
