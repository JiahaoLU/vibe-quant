from abc import ABC, abstractmethod

from ..events import BarBundleEvent


class Strategy(ABC):
    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> None:
        """Consume a BarBundleEvent and emit a SignalBundleEvent if conditions are met."""
        ...
