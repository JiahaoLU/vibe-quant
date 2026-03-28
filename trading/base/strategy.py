from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, Event, SignalBundleEvent, TickEvent


class Strategy(ABC):
    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        self._emit     = emit
        self._get_bars = get_bars

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    def get_signals(self, event: BarBundleEvent) -> None:
        result = self.calculate_signals(event)
        if result is not None:
            self._emit(result)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        """Compute signals from a bar bundle. Return a SignalBundleEvent or None."""
        ...
