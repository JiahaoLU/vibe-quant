from abc import ABC, abstractmethod
from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..events import BarBundleEvent, Event, SignalBundleEvent, TickEvent


class StrategyBase(ABC):
    """Abstract base for trading strategies. Receives bar bundles and emits signals via the injected emit callable. get_bars provides read-only access to bar history for indicator calculation."""
    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        self._emit     = emit
        self._get_bars = get_bars

    @abstractmethod
    def get_signals(self, event: BarBundleEvent) -> None:
        """Process a bar bundle. May emit zero or more SignalBundleEvents."""
        ...


class Strategy(StrategyBase):
    strategy_params: StrategyParams

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
        strategy_params: StrategyParams
    ):
        super().__init__(emit, get_bars)
        self.strategy_params = strategy_params
        self._init(strategy_params)

    @property
    def symbols(self) -> list[str]:
        return self.strategy_params.symbols

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    def get_signals(self, event: BarBundleEvent) -> None:
        result = self.calculate_signals(event)
        if result is not None:
            self._emit(result)

    @abstractmethod
    def _init(self, strategy_params: StrategyParams):
        ...

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        """Compute signals from a bar bundle. Return a SignalBundleEvent or None."""
        ...
