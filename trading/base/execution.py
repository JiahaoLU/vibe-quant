from abc import ABC, abstractmethod

from ..events import OrderEvent


class ExecutionHandler(ABC):
    @abstractmethod
    def execute_order(self, event: OrderEvent) -> None:
        """Simulate or route the order and emit a FillEvent."""
        ...
