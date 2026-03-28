from typing import Callable

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

    def add(self, strategy_class: type[StrategyBase], /, **kwargs) -> None:
        """Factory: construct a strategy, injecting emit and get_bars as defaults."""
        kwargs.setdefault("emit", self._emit)
        kwargs.setdefault("get_bars", self._get_bars)
        self._strategies.append(strategy_class(**kwargs))

    def add_strategy(self, strategy: StrategyBase) -> None:
        """Add a pre-constructed strategy instance."""
        self._strategies.append(strategy)

    def get_signals(self, event: BarBundleEvent) -> None:
        for strategy in self._strategies:
            strategy.get_signals(event)
