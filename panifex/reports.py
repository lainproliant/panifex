# --------------------------------------------------------------------
# reports.py: Reporting and result aggregation in JSON format.
#
# Author: Lain Musgrove (lain.proliant@gmail.com)
# Date: Thursday, January 2 2020
#
# Distributed under terms of the MIT license.
# --------------------------------------------------------------------
import getpass
import uuid
from dataclasses import dataclass, field
from datetime import datetime

from typing import List, Optional
from .util import format_dt


# --------------------------------------------------------------------
# pylint: disable=R0201
@dataclass
class Report:
    name: str
    started: Optional[datetime]
    finished: Optional[datetime]

    def __post_init__(self):
        self.id = str(uuid.uuid4())

    def succeeded(self) -> bool:
        return True

    def failed(self) -> bool:
        return not self.succeeded()

    def generate(self):
        return {
            "type": type(self).__qualname__,
            "name": self.name,
            "id": self.id,
            "started": format_dt(self.started),
            "finished": format_dt(self.finished),
            "succeeded": self.succeeded(),
        }


# --------------------------------------------------------------------
@dataclass
class BuildReport(Report):
    name: str
    started: Optional[datetime]
    finished: Optional[datetime]
    job_reports: List[Report] = field(default_factory=list)

    def __post_init__(self):
        super().__post_init__()
        self.job_reports.sort(key=lambda x: x.started)

    def generate(self):
        return {
            **super().generate(),
            "user": getpass.getuser(),
            "jobs": {j.id: j.generate() for j in self.job_reports},
        }
