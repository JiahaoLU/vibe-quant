from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, TickEvent


class DataHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def update_bars(self) -> bool:
        """Emit the next bar bundle as a BarBundleEvent. Returns False when data is exhausted."""
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        """Return the last N bars for a symbol."""
        ...
