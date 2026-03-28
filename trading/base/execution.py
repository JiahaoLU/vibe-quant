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
