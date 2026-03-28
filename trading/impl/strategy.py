import queue

from ..base.data import DataHandler
from ..base.strategy import Strategy
from ..events import BarBundleEvent, SignalBundleEvent, SignalEvent


class SMACrossoverStrategy(Strategy):
    """
    Emits LONG when the fast SMA crosses above the slow SMA for a symbol.
    Emits EXIT when the fast SMA crosses below the slow SMA.
    Operates on multiple symbols simultaneously.
    """

    def __init__(
        self,
        events:  queue.Queue,
        data:    DataHandler,
        symbols: list[str],
        fast:    int = 10,
        slow:    int = 30,
    ):
        self._events   = events
        self._data     = data
        self._symbols  = symbols
        self._fast     = fast
        self._slow     = slow
        self._position: dict[str, str | None] = {s: None for s in symbols}

    def calculate_signals(self, event: BarBundleEvent) -> None:
        signals: dict[str, SignalEvent] = {}

        for symbol in self._symbols:
            bars = self._data.get_latest_bars(symbol, self._slow)
            if len(bars) < self._slow:
                continue

            closes   = [b["close"] for b in bars]
            fast_sma = sum(closes[-self._fast:]) / self._fast
            slow_sma = sum(closes) / self._slow

            if fast_sma > slow_sma and self._position[symbol] != "LONG":
                self._position[symbol] = "LONG"
                signals[symbol] = SignalEvent(
                    symbol      = symbol,
                    timestamp   = event.timestamp,
                    signal_type = "LONG",
                )
            elif fast_sma < slow_sma and self._position[symbol] == "LONG":
                self._position[symbol] = None
                signals[symbol] = SignalEvent(
                    symbol      = symbol,
                    timestamp   = event.timestamp,
                    signal_type = "EXIT",
                )

        if signals:
            self._events.put(SignalBundleEvent(
                timestamp = event.timestamp,
                signals   = signals,
            ))
