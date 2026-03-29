from dataclasses import dataclass

from trading.base.strategy_params import StrategyParams

from trading.base.strategy import Strategy
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent

@dataclass
class SMACrossoverStrategyParams(StrategyParams):
    symbols:  list[str]
    fast:     int = 10
    slow:     int = 30


class SMACrossoverStrategy(Strategy):
    """
    Emits LONG when the fast SMA crosses above the slow SMA for a symbol.
    Emits EXIT when the fast SMA crosses below the slow SMA.
    Operates on multiple symbols simultaneously.
    """

    def _init(
        self,
        strategy_params: StrategyParams
    ):
        self._symbols  = strategy_params.symbols
        if type(strategy_params) is SMACrossoverStrategyParams:
            self._fast     = strategy_params.fast
            self._slow     = strategy_params.slow
        self._position: dict[str, str | None] = {s: None for s in self._symbols }

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        signals: dict[str, SignalEvent] = {}

        for symbol in self._symbols:
            bars = self.get_bars(symbol, self._slow)
            if len(bars) < self._slow:
                continue

            closes   = [b.close for b in bars]
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

        return SignalBundleEvent(timestamp=event.timestamp, signals=signals) if signals else None
