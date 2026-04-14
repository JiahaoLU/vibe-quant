import asyncio
import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Callable
from zoneinfo import ZoneInfo

from ...base.data import DataHandler
from ...events import BarBundleEvent, Event, TickEvent
from external.alpaca import fetch_bars, fetch_bars_history

ET = ZoneInfo("America/New_York")
_DAILY_BAR_HOUR   = 16
_DAILY_BAR_MINUTE = 5
logger = logging.getLogger(__name__)


class AlpacaDataHandler(DataHandler):
    """
    Live DataHandler backed by Alpaca's market data API.

    bar_freq: "1d" for daily bars, "Xm" for X-minute intraday bars (e.g. "5m").

    update_bars_async() sleeps until the next bar boundary, fetches the
    completed bar for all symbols, pushes to internal deques, and emits a
    BarBundleEvent. Returns False if request_shutdown() was called.
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        bar_freq:    str,
        api_key:     str,
        secret:      str,
        max_history: int = 200,
    ):
        super().__init__(emit, bar_freq=bar_freq)
        self._symbols        = symbols
        self._api_key        = api_key
        self._secret         = secret
        self._max_history    = max_history
        self._deques: dict[str, deque] = {s: deque(maxlen=max_history) for s in symbols}
        self._shutdown_event = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def prefill(self) -> None:
        """Warm deques with historical bars before the live loop starts.

        Window:
          - daily bars:    max_history * 2 calendar days (~max_history trading days)
          - intraday bars: max_history * bar_minutes * 3 minutes (3× buffer covers
                           non-trading hours and weekends without fetching months of data)

        Any exception from fetch_bars_history (network, auth) propagates and
        aborts startup intentionally — trading with empty deques produces
        incorrect signals, so fail-fast is the right policy.
        """
        now = datetime.now(tz=ET)
        if self._bar_freq == "1d":
            start = now - timedelta(days=self._max_history * 2)
        else:
            bar_minutes = int(self._bar_freq.rstrip("m"))
            start = now - timedelta(minutes=self._max_history * bar_minutes * 3)
        history = fetch_bars_history(
            symbols=self._symbols,
            bar_freq=self._bar_freq,
            start=start,
            end=now,
            api_key=self._api_key,
            secret=self._secret,
        )

        for symbol in self._symbols:
            raw_bars = history.get(symbol)
            if not raw_bars:
                logger.warning(
                    "prefill: no history returned for %s; deque will remain empty at startup",
                    symbol,
                )
                continue
            for raw in raw_bars:
                self._deques[symbol].append(
                    TickEvent(
                        symbol=symbol,
                        timestamp=raw["timestamp"],
                        open=raw["open"],
                        high=raw["high"],
                        low=raw["low"],
                        close=raw["close"],
                        volume=raw["volume"],
                    )
                )
            logger.info(
                "prefill: loaded %d bars for %s (max_history=%d)",
                len(self._deques[symbol]),
                symbol,
                self._max_history,
            )

    def update_bars(self) -> bool:
        """Synchronous fallback — not used in live; runs asyncio internally."""
        return asyncio.run(self.update_bars_async())

    async def update_bars_async(self) -> bool:
        if self._shutdown_event.is_set():
            return False

        sleep_secs = self._seconds_until_next_bar()
        if sleep_secs > 0:
            sleep_task    = asyncio.create_task(asyncio.sleep(sleep_secs))
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            done, pending = await asyncio.wait(
                [sleep_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if self._shutdown_event.is_set():
                return False

        now = datetime.now(tz=ET)
        bars = fetch_bars(
            symbols  = self._symbols,
            bar_freq = self._bar_freq,
            start    = now - timedelta(days=3 if self._bar_freq == "1d" else 0, minutes=60),
            end      = now,
            api_key  = self._api_key,
            secret   = self._secret,
        )

        bundle_bars: dict[str, TickEvent] = {}
        for symbol in self._symbols:
            raw = bars.get(symbol)
            if raw is None:
                continue
            tick = TickEvent(
                symbol    = symbol,
                timestamp = raw["timestamp"],
                open      = raw["open"],
                high      = raw["high"],
                low       = raw["low"],
                close     = raw["close"],
                volume    = raw["volume"],
            )
            self._deques[symbol].append(tick)
            bundle_bars[symbol] = tick

        if bundle_bars:
            ts = next(iter(bundle_bars.values())).timestamp
            self._emit(BarBundleEvent(timestamp=ts, bars=bundle_bars))

        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        dq = self._deques.get(symbol, deque())
        return list(dq)[-n:] if dq else []

    def _seconds_until_next_bar(self) -> float:
        now = datetime.now(tz=ET)
        if self._bar_freq == "1d":
            target = now.replace(hour=_DAILY_BAR_HOUR, minute=_DAILY_BAR_MINUTE,
                                 second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                while target.weekday() >= 5:   # skip weekends
                    target += timedelta(days=1)
            return max(0.0, (target - now).total_seconds())
        else:
            minutes = int(self._bar_freq.rstrip("m"))
            next_min = ((now.minute // minutes) + 1) * minutes
            delta_min = next_min - now.minute
            target = now.replace(second=0, microsecond=0) + timedelta(minutes=delta_min)
            return max(0.0, (target - now).total_seconds())
