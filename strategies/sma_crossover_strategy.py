from dataclasses import dataclass

from trading.base.strategy_params import StrategyParams

from trading.base.strategy import Strategy
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent


@dataclass
class SMACrossoverStrategyParams(StrategyParams):
    symbols: list[str]
    fast:    int = 10
    slow:    int = 30


class SMACrossoverStrategy(Strategy):
    """
    Emits a SignalBundleEvent covering all symbols whenever any position changes.
    Each long position receives an equal share of the strategy's nominal (signal
    weights sum to 1 across active longs).  A symbol with no position gets 0.
    """

    def _init(self, strategy_params: StrategyParams):
        self._symbols = strategy_params.symbols
        if isinstance(strategy_params, SMACrossoverStrategyParams):
            self._fast = strategy_params.fast
            self._slow = strategy_params.slow
        self._position: dict[str, str | None] = {s: None for s in self._symbols}

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        changed = False

        for symbol in self._symbols:
            bars = self.get_bars(symbol, self._slow)
            if len(bars) < self._slow:
                continue

            closes   = [b.close for b in bars]
            fast_sma = sum(closes[-self._fast:]) / self._fast
            slow_sma = sum(closes) / self._slow

            prev = self._position[symbol]
            if fast_sma > slow_sma and prev != "LONG":
                self._position[symbol] = "LONG"
                changed = True
            elif fast_sma <= slow_sma and prev == "LONG":
                self._position[symbol] = None
                changed = True

        if not changed:
            return None

        # Normalise: equal weight across active long positions so weights sum to 1
        longs = [s for s in self._symbols if self._position[s] == "LONG"]
        weight = 1.0 / len(longs) if longs else 0.0

        signals = {
            symbol: SignalEvent(
                symbol    = symbol,
                timestamp = event.timestamp,
                signal    = weight if self._position[symbol] == "LONG" else 0.0,
            )
            for symbol in self._symbols
        }
        return SignalBundleEvent(timestamp=event.timestamp, signals=signals)
