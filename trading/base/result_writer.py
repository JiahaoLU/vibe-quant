from abc import ABC, abstractmethod

from .portfolio import Portfolio


class BacktestResultWriter(ABC):
    @abstractmethod
    def write(self, portfolio: Portfolio) -> None: ...
