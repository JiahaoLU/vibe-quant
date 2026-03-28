import csv
import queue
from collections import deque
from datetime import datetime

from ..base.data import DataHandler
from ..events import BarBundleEvent, TickEvent


class MultiCSVDataHandler(DataHandler):
    """
    Loads N CSVs (one per symbol), computes the union of all timestamps,
    and replays one BarBundleEvent per timestep. Missing bars are zero-filled.
    """

    def __init__(
        self,
        events: queue.Queue,
        symbols: list[str],
        csv_paths: list[str],
        max_history: int = 200,
        date_format: str = "%Y-%m-%d",
    ):
        if len(symbols) != len(csv_paths):
            raise ValueError(
                f"symbols and csv_paths must have the same length "
                f"(got {len(symbols)} and {len(csv_paths)})"
            )
        self._events  = events
        self._symbols = symbols

        raw: dict[str, dict[datetime, TickEvent]] = {}
        for symbol, path in zip(symbols, csv_paths):
            raw[symbol] = self._load(symbol, path, date_format)

        all_ts: set[datetime] = set()
        for data in raw.values():
            all_ts.update(data.keys())
        timeline = sorted(all_ts)

        self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
        for ts in timeline:
            bundle = {
                symbol: raw[symbol].get(
                    ts,
                    TickEvent(symbol=symbol, timestamp=ts, open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0),
                )
                for symbol in symbols
            }
            self._merged.append((ts, bundle))

        self._index = 0
        self._history: dict[str, deque] = {
            s: deque(maxlen=max_history) for s in symbols
        }

    def _load(self, symbol: str, path: str, date_format: str) -> dict[datetime, TickEvent]:
        result: dict[datetime, TickEvent] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = datetime.strptime(row["timestamp"], date_format)
                result[ts] = TickEvent(
                    symbol    = symbol,
                    timestamp = ts,
                    open      = float(row["open"]),
                    high      = float(row["high"]),
                    low       = float(row["low"]),
                    close     = float(row["close"]),
                    volume    = float(row["volume"]),
                )
        return result

    def update_bars(self) -> bool:
        if self._index >= len(self._merged):
            return False
        ts, bars = self._merged[self._index]
        self._index += 1
        for symbol, bar in bars.items():
            self._history[symbol].append(bar)
        self._events.put(BarBundleEvent(timestamp=ts, bars=bars))
        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        bars = list(self._history[symbol])
        return bars[-n:] if len(bars) >= n else bars
