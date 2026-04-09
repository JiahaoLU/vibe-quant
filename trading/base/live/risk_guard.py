from abc import ABC, abstractmethod

from ...events import StrategyBundleEvent


class RiskGuard(ABC):
    @abstractmethod
    def check(
        self,
        event: StrategyBundleEvent,
        current_prices: dict[str, float],
        current_equity: float,
    ) -> StrategyBundleEvent | None:
        """Return event (possibly modified) or None to halt trading."""
        ...

    @abstractmethod
    def reset_day(self, current_equity: float) -> None:
        """Snapshot day-open equity. Call at start of each session."""
        ...
