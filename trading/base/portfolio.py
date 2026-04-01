from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, Event, FillEvent, StrategyBundleEvent


class Portfolio(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None: ...

    @abstractmethod
    def on_signal(self, event: StrategyBundleEvent) -> None: ...

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None: ...

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...

    @property
    @abstractmethod
    def strategy_pnl(self) -> list[dict]: ...

    @property
    @abstractmethod
    def strategy_traded_value(self) -> dict[str, float]: ...
