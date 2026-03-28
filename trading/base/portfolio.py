from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, FillEvent, SignalBundleEvent


class Portfolio(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def on_signal(self, event: SignalBundleEvent) -> None: ...

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None: ...

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...
