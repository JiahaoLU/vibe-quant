from abc import ABC, abstractmethod
from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..events import BarBundleEvent, Event, SignalBundleEvent, TickEvent


class StrategyBase(ABC):
    """Common base for all strategy components. Provides get_bars injection and declares the symbols contract."""
    def __init__(self, get_bars: Callable[[str, int], list[TickEvent]]):
        self._get_bars = get_bars

    @property
    @abstractmethod
    def symbols(self) -> list[str]:
        """All symbols this component operates on."""
        ...


class StrategySignalGenerator(StrategyBase):
    """ABC for components that receive bar bundles and emit signal bundles."""

    @property
    @abstractmethod
    def required_freq(self) -> str:
        """The finest bar_freq needed across all contained strategies."""
        ...

    @abstractmethod
    def emit(self, event: Event) -> None:
        """Emit an event downstream."""
        ...

    @abstractmethod
    def get_signals(self, event: BarBundleEvent) -> None:
        """Process a bar bundle and emit zero or more SignalBundleEvents."""
        ...


class Strategy(StrategyBase):
    """Researcher-facing base class. Implement calculate_signals and _init; override on_get_signal for custom post-signal logic."""
    strategy_params: StrategyParams

    def __init__(
        self,
        get_bars:        Callable[[str, int], list[TickEvent]],
        strategy_params: StrategyParams,
    ):
        super().__init__(get_bars=get_bars)
        self.strategy_params = strategy_params
        self._init(strategy_params)

    @property
    def symbols(self) -> list[str]:
        return self.strategy_params.symbols

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    def on_get_signal(self, result: SignalBundleEvent | None) -> None:
        """Hook called after calculate_signals, whether or not a bundle was produced. Override for custom post-signal actions."""

    @abstractmethod
    def _init(self, strategy_params: StrategyParams):
        ...

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        """Compute signals from a bar bundle. Return a SignalBundleEvent or None."""
        ...
