import asyncio
from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, TickEvent


class DataHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def prefill(self) -> None:
        """Warm any in-memory history needed before bar processing begins."""
        ...

    @abstractmethod
    def update_bars(self) -> bool:
        """Emit the next bar bundle as a BarBundleEvent. Returns False when data is exhausted."""
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        """Return the last N bars for a symbol."""
        ...

    async def update_bars_async(self) -> bool:
        """Default: wraps update_bars() via asyncio.to_thread. Override for real async."""
        return await asyncio.to_thread(self.update_bars)
