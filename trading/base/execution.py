import asyncio
from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, OrderEvent


class ExecutionHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def execute_order(self, event: OrderEvent) -> None:
        """Simulate or route the order and emit a FillEvent."""
        ...

    async def execute_order_async(self, event: OrderEvent) -> None:
        """Default: wraps execute_order() via asyncio.to_thread. Override for real async."""
        await asyncio.to_thread(self.execute_order, event)
