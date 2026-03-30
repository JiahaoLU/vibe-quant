from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..base.strategy import StrategyBase
from ..events import BarBundleEvent, Event, TickEvent


class StrategyContainer(StrategyBase):
    """
    Holds multiple strategies and dispatches BarBundleEvents to each.
    Each contained strategy emits its own SignalBundleEvent independently.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(emit, get_bars)
        self._strategies: list[StrategyBase] = []

    @property
    def symbols(self) -> list[str]:
        """Union of symbols across all contained strategies (order-preserving, deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for s in self._strategies:
            for sym in getattr(s, "symbols", []):
                if sym not in seen:
                    seen.add(sym)
                    result.append(sym)
        return result

    def add(self, strategy_class: type[StrategyBase], strategy_params: StrategyParams, *, emit=None, get_bars=None) -> None:
        """Factory: construct a strategy, injecting emit and get_bars as defaults."""
        kwargs = {
            "emit":            emit     if emit     is not None else self._emit,
            "get_bars":        get_bars if get_bars is not None else self._get_bars,
            "strategy_params": strategy_params,
        }
        self._strategies.append(strategy_class(**kwargs))

    def add_strategy(self, strategy: StrategyBase) -> None:
        """Add a pre-constructed strategy instance."""
        self._strategies.append(strategy)

    def get_signals(self, event: BarBundleEvent) -> None:
        for strategy in self._strategies:
            strategy.get_signals(event)
