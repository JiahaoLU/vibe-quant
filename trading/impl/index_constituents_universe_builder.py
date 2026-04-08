import csv
from datetime import datetime

from ..base import UniverseBuilder


class IndexConstituentsUniverseBuilder(UniverseBuilder):
    _DATE_FMT = "%Y-%m-%d"

    def __init__(self, manifest_path: str):
        self._universe: dict[str, tuple[datetime, datetime | None]] = {}
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                enter = datetime.strptime(row["enter_date"], self._DATE_FMT)
                exit_ = (
                    datetime.strptime(row["exit_date"], self._DATE_FMT)
                    if row["exit_date"].strip()
                    else None
                )
                self._universe[row["symbol"]] = (enter, exit_)

    def is_active(self, symbol: str, timestamp: datetime) -> bool:
        window = self._universe.get(symbol)
        if window is None:
            return False
        enter, exit_ = window
        return enter <= timestamp and (exit_ is None or timestamp < exit_)
