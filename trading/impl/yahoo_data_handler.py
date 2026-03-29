import csv
import os
from collections import deque
from datetime import datetime
from typing import Callable

from ..base.data import DataHandler
from ..events import BarBundleEvent, Event, TickEvent


class YahooDataHandler(DataHandler):
    """
    Fetches historical daily bars via an injected fetch callable at construction,
    then replays them one BarBundleEvent per timestep.

    Parameters
    ----------
    emit        : event queue put method
    symbols     : list of ticker symbols, e.g. ["AAPL", "MSFT"]
    start       : ISO date string, inclusive, e.g. "2020-01-01"
    end         : ISO date string, exclusive, e.g. "2022-01-01"
    fetch       : callable(symbol, start, end) -> list[dict] with keys
                  timestamp, open, high, low, close, volume
    max_history : maximum bar history kept per symbol
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        start:       str,
        end:         str,
        fetch:       Callable[[list[str], str, str], dict[str, list[dict]]],
        max_history: int = 200,
    ):
        super().__init__(emit)
        self._symbols = symbols

        all_rows = fetch(symbols, start, end)
        raw: dict[str, dict[datetime, TickEvent]] = {}
        for symbol, rows in all_rows.items():
            raw[symbol] = {
                row["timestamp"]: TickEvent(
                    symbol    = symbol,
                    timestamp = row["timestamp"],
                    open      = row["open"],
                    high      = row["high"],
                    low       = row["low"],
                    close     = row["close"],
                    volume    = row["volume"],
                )
                for row in rows
            }

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
        self._history: dict[str, deque] = {s: deque(maxlen=max_history) for s in symbols}
        self._save_bars(raw)

    def _save_bars(self, raw: dict[str, dict[datetime, TickEvent]]) -> None:
        os.makedirs("results", exist_ok=True)
        for symbol, bars in raw.items():
            path = os.path.join("results", f"{symbol}_yahoo.csv")
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for ts in sorted(bars):
                    bar = bars[ts]
                    writer.writerow([ts.strftime("%Y-%m-%d"), bar.open, bar.high, bar.low, bar.close, bar.volume])

    def update_bars(self) -> bool:
        if self._index >= len(self._merged):
            return False
        ts, bars = self._merged[self._index]
        self._index += 1
        for symbol, bar in bars.items():
            self._history[symbol].append(bar)
        self._emit(BarBundleEvent(timestamp=ts, bars=bars))
        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        bars = list(self._history[symbol])
        return bars[-n:] if len(bars) >= n else bars
