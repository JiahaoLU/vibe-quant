import logging
from datetime import date

from ...base.live.risk_guard import RiskGuard as RiskGuardBase
from ...events import SignalEvent, StrategyBundleEvent

logger = logging.getLogger(__name__)


class RiskGuard(RiskGuardBase):
    """
    Two checks applied before each signal bundle reaches the portfolio:

    1. Daily loss limit: if equity has fallen more than max_daily_loss_pct from
       the day's opening equity, halt all new signals for the session.

    2. Per-symbol position cap: clamp each signal weight so the resulting
       nominal allocation does not exceed max_position_pct × current_equity.

    reset_day(equity) must be called at each session open.
    The guard also auto-resets when the event timestamp moves to a new calendar date.
    """

    def __init__(
        self,
        max_daily_loss_pct: float,
        max_position_pct: float,
        initial_capital: float,
    ):
        self._max_daily_loss_pct = max_daily_loss_pct
        self._max_position_pct   = max_position_pct
        self._initial_capital    = initial_capital
        self._day_open_equity: float | None = None
        self._last_reset_date: date | None  = None

    def reset_day(self, current_equity: float) -> None:
        """Set day-open equity. _last_reset_date is updated by check() on first event of each day."""
        self._day_open_equity = current_equity

    def check(
        self,
        event: StrategyBundleEvent,
        current_prices: dict[str, float],
        current_equity: float,
    ) -> StrategyBundleEvent | None:
        # Auto-reset on new trading day (compares consecutive event dates)
        event_date = event.timestamp.date()
        if self._last_reset_date is not None and self._last_reset_date != event_date:
            self._day_open_equity = current_equity
        self._last_reset_date = event_date

        # Daily loss limit
        if (
            self._day_open_equity is not None
            and current_equity < self._day_open_equity * (1 - self._max_daily_loss_pct)
        ):
            logger.warning(
                "RiskGuard: daily loss limit breached. equity=%.2f day_open=%.2f limit=%.1f%%",
                current_equity,
                self._day_open_equity,
                self._max_daily_loss_pct * 100,
            )
            return None

        # Per-symbol position cap
        max_signal = (self._max_position_pct * current_equity) / self._initial_capital
        capped: dict[str, SignalEvent] = {}
        for symbol, sig_event in event.combined.items():
            capped_weight = min(sig_event.signal, max_signal) if sig_event.signal > 0 else sig_event.signal
            capped[symbol] = SignalEvent(
                symbol=symbol,
                timestamp=sig_event.timestamp,
                signal=capped_weight,
            )

        return StrategyBundleEvent(
            timestamp=event.timestamp,
            combined=capped,
            per_strategy=event.per_strategy,
        )
