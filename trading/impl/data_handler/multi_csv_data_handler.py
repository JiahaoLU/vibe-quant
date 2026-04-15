import csv
import math
import os
import random
from collections import deque
from datetime import date, datetime, timedelta
from typing import Callable

from ...base.data import DataHandler
from ...base.universe_builder import UniverseBuilder
from ...events import BarBundleEvent, Event, TickEvent


class MultiCSVDataHandler(DataHandler):
    """
    Loads OHLCV data from CSVs or generates it randomly, then replays one
    BarBundleEvent per timestep.

    CSV mode  — pass csv_paths:
        MultiCSVDataHandler(emit, symbols, csv_paths=[...])

    Random mode — pass start and end instead:
        MultiCSVDataHandler(emit, symbols, start="2020-01-01", end="2022-01-01")

    In random mode, weekday bars are generated via Gaussian random walk.
    Results are reproducible: each symbol uses hash(symbol) as its RNG seed.
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        csv_paths:   list[str] | None = None,
        start:       str | None = None,
        end:         str | None = None,
        max_history: int = 200,
        date_format: str = "%Y-%m-%d",
        universe_builder: UniverseBuilder | None = None,
        bar_freq:    str = "1d",
    ):
        if csv_paths is None and (start is None or end is None):
            raise ValueError(
                "Provide either csv_paths or both start and end for random generation."
            )
        if csv_paths is not None and len(symbols) != len(csv_paths):
            raise ValueError(
                f"symbols and csv_paths must have the same length "
                f"(got {len(symbols)} and {len(csv_paths)})"
            )
        super().__init__(emit, bar_freq=bar_freq)
        self._symbols = symbols

        raw: dict[str, dict[datetime, TickEvent]] = {}
        if csv_paths is not None:
            for symbol, path in zip(symbols, csv_paths):
                raw[symbol] = self._load(symbol, path, date_format)
        else:
            for symbol in symbols:
                raw[symbol] = self._generate(symbol, start, end)

        all_ts: set[datetime] = set()
        for data in raw.values():
            all_ts.update(data.keys())
        timeline = sorted(all_ts)

        last_real: dict[str, TickEvent | None] = {s: None for s in symbols}
        was_active: dict[str, bool] = {s: True for s in symbols}
        self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
        for ts in timeline:
            bundle: dict[str, TickEvent] = {}
            for symbol in symbols:
                if ts in raw[symbol]:
                    bar = raw[symbol][ts]
                    last_real[symbol] = bar
                elif last_real[symbol] is not None:
                    prev = last_real[symbol]
                    bar = TickEvent(
                        symbol=symbol, timestamp=ts,
                        open=prev.close, high=prev.close, low=prev.close, close=prev.close,
                        volume=0.0, is_synthetic=True,
                    )
                else:
                    bar = TickEvent(
                        symbol=symbol, timestamp=ts,
                        open=0.0, high=0.0, low=0.0, close=0.0,
                        volume=0.0, is_synthetic=True,
                    )

                if universe_builder is not None:
                    is_now_active = universe_builder.is_active(symbol, ts)
                    if not is_now_active and was_active[symbol]:
                        bar = TickEvent(
                            symbol=bar.symbol,
                            timestamp=bar.timestamp,
                            open=bar.open,
                            high=bar.high,
                            low=bar.low,
                            close=bar.close,
                            volume=bar.volume,
                            is_synthetic=bar.is_synthetic,
                            is_delisted=True,
                        )
                    elif not is_now_active:
                        was_active[symbol] = False
                        continue
                    was_active[symbol] = is_now_active

                bundle[symbol] = bar
            self._merged.append((ts, bundle))

        self._index = 0
        self._history: dict[str, deque] = {
            s: deque(maxlen=max_history) for s in symbols
        }
        self._save_bars(raw, "csv")

    @staticmethod
    def _freq_to_delta(freq: str) -> timedelta:
        unit  = freq[-1]
        value = int(freq[:-1])
        if unit == 'd':
            return timedelta(days=value)
        if unit == 'h':
            return timedelta(hours=value)
        if unit == 'm':
            return timedelta(minutes=value)
        if unit == 's':
            return timedelta(seconds=value)
        raise ValueError(f"Unsupported bar_freq: {freq!r}")

    def _save_bars(self, raw: dict[str, dict[datetime, "TickEvent"]], suffix: str) -> None:
        intraday = self._freq_to_delta(self._bar_freq) < timedelta(days=1)
        ts_fmt   = "%Y-%m-%d %H:%M" if intraday else "%Y-%m-%d"
        os.makedirs("results", exist_ok=True)
        for symbol, bars in raw.items():
            path = os.path.join("results", f"{symbol}_{suffix}.csv")
            with open(path, "w", newline="") as f:
                writer = csv.writer(f)
                writer.writerow(["timestamp", "open", "high", "low", "close", "volume"])
                for ts in sorted(bars):
                    bar = bars[ts]
                    writer.writerow([ts.strftime(ts_fmt), bar.open, bar.high, bar.low, bar.close, bar.volume])

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

    def _generate(self, symbol: str, start: str, end: str) -> dict[datetime, TickEvent]:
        rng        = random.Random(hash(symbol) % (2 ** 31))
        start_date = date.fromisoformat(start)
        end_date   = date.fromisoformat(end)
        price      = 100.0
        result: dict[datetime, TickEvent] = {}
        delta      = self._freq_to_delta(self._bar_freq)

        # Scale daily drift/vol to per-bar using sqrt-of-time.
        # One trading day = 390 minutes; daily params: drift=0.0003, vol=0.015.
        _TRADING_MIN = 390.0
        bar_minutes  = delta.total_seconds() / 60
        if bar_minutes >= _TRADING_MIN:
            # daily or multi-day: use daily params as-is
            drift, vol, wick_vol = 0.0003, 0.015, 0.005
            vol_scale = bar_minutes / _TRADING_MIN  # just for volume
        else:
            scale     = math.sqrt(bar_minutes / _TRADING_MIN)
            drift     = 0.0003 * (bar_minutes / _TRADING_MIN)
            vol       = 0.015  * scale
            wick_vol  = 0.005  * scale
            vol_scale = bar_minutes / _TRADING_MIN

        current = start_date
        while current < end_date:
            if current.weekday() < 5:
                if bar_minutes >= _TRADING_MIN:
                    ts     = datetime(current.year, current.month, current.day)
                    change = rng.gauss(drift, vol)
                    open_  = price
                    close  = round(open_ * (1 + change), 4)
                    high   = round(max(open_, close) * (1 + abs(rng.gauss(0, wick_vol))), 4)
                    low    = round(min(open_, close) * (1 - abs(rng.gauss(0, wick_vol))), 4)
                    volume = float(int(rng.uniform(500_000, 5_000_000)))
                    result[ts] = TickEvent(
                        symbol=symbol, timestamp=ts,
                        open=open_, high=high, low=low, close=close, volume=volume,
                    )
                    price = close
                else:
                    bar_ts     = datetime(current.year, current.month, current.day, 9, 30)
                    market_end = datetime(current.year, current.month, current.day, 16, 0)
                    while bar_ts < market_end:
                        change = rng.gauss(drift, vol)
                        open_  = price
                        close  = round(open_ * (1 + change), 4)
                        high   = round(max(open_, close) * (1 + abs(rng.gauss(0, wick_vol))), 4)
                        low    = round(min(open_, close) * (1 - abs(rng.gauss(0, wick_vol))), 4)
                        volume = float(int(rng.uniform(
                            500_000 * vol_scale, 5_000_000 * vol_scale
                        )))
                        result[bar_ts] = TickEvent(
                            symbol=symbol, timestamp=bar_ts,
                            open=open_, high=high, low=low, close=close, volume=volume,
                        )
                        price  = close
                        bar_ts += delta
            current += timedelta(days=1)
        return result

    def prefill(self) -> None:
        """Backtest data is already loaded during initialization."""
        return None

    def update_bars(self) -> bool:
        if self._index >= len(self._merged):
            return False
        ts, bars = self._merged[self._index]
        self._index += 1
        is_eod = (
            self._index >= len(self._merged)
            or self._merged[self._index][0].date() != ts.date()
        )
        for symbol, bar in bars.items():
            if not bar.is_synthetic:
                self._history[symbol].append(bar)
        self._emit(BarBundleEvent(timestamp=ts, bars=bars, is_end_of_day=is_eod))
        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        bars = list(self._history[symbol])
        return bars[-n:] if len(bars) >= n else bars
