from abc import ABC, abstractmethod

from ...base.portfolio import Portfolio


class PositionReconciler(ABC):
    @abstractmethod
    async def hydrate(self, portfolio: Portfolio) -> None:
        """Query broker state and call portfolio.restore(holdings, cash)."""
        ...
