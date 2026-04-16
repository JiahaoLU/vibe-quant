from abc import ABC, abstractmethod

from ...events import FillEvent, OrderEvent, StrategyBundleEvent


class TradeLogger(ABC):
    """Persist every signal, order, and fill event for audit and post-trade analysis."""

    @abstractmethod
    def open_session(self, session_id: str, mode: str, strategy_names: list[str]) -> None:
        """Record the start of a new trading session."""
        ...

    @abstractmethod
    def log_signal(self, session_id: str, event: StrategyBundleEvent) -> None:
        """Log a strategy signal bundle (one row per strategy×symbol)."""
        ...

    @abstractmethod
    def log_order(self, session_id: str, event: OrderEvent) -> None:
        """Log an order intent. HOLD orders must be silently ignored."""
        ...

    @abstractmethod
    def log_fill(self, session_id: str, event: FillEvent) -> None:
        """Log an execution fill. HOLD fills must be silently ignored."""
        ...

    @abstractmethod
    def log_snapshot(self, session_id: str, snapshot: dict) -> None:
        """Log a PnL snapshot after each fill (latest equity_curve row from Portfolio)."""
        ...

    @abstractmethod
    def close_session(self, session_id: str) -> None:
        """Record the end of a trading session."""
        ...
