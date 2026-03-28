from abc import ABC, abstractmethod

from ..events import FillEvent, SignalBundleEvent


class Portfolio(ABC):
    @abstractmethod
    def on_signal(self, event: SignalBundleEvent) -> None: ...

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None: ...

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...
