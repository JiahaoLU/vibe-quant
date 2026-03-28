from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, TickEvent


class Strategy(ABC):
    def __init__(self, get_bars: Callable[[str, int], list[TickEvent]]):
        self._get_bars = get_bars

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> None:
        """Consume a BarBundleEvent and emit a SignalBundleEvent if conditions are met."""
        ...
