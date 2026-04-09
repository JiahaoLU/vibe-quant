from datetime import datetime
from trading.events import SignalEvent, StrategyBundleEvent


def _bundle(signals: dict[str, float], ts=None) -> StrategyBundleEvent:
    ts = ts or datetime(2024, 1, 2, 16, 5)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={
            sym: SignalEvent(symbol=sym, timestamp=ts, signal=sig)
            for sym, sig in signals.items()
        },
        per_strategy={"s1": {sym: 1.0 for sym in signals}},
    )


def test_check_passes_event_when_within_limits():
    from trading.impl.risk_guard.risk_guard import RiskGuard

    # max_position_pct=0.60: max_signal = 0.60 * 10_000 / 10_000 = 0.60
    # signal=0.5 < 0.60 → not clamped; equity drop 0% < 5% limit → not halted
    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.60, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=10_000.0)

    assert result is not None
    assert result.combined["AAPL"].signal == 0.5


def test_check_returns_none_when_daily_loss_limit_breached():
    from trading.impl.risk_guard.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    # equity dropped 6% — exceeds 5% limit
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=9_400.0)

    assert result is None


def test_check_clamps_signal_when_position_cap_exceeded():
    from trading.impl.risk_guard.risk_guard import RiskGuard

    # initial_capital=10_000, max_position_pct=0.10
    # At price=100, signal=0.5 → target_qty = 0.5 * 10000 / 100 = 50 shares = $5000 = 50% of equity
    # max_position = 0.10 * 10000 = $1000 → max_signal = 0.10 * 10000 / 10000 = 0.10
    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.10, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    result = guard.check(event, current_prices={"AAPL": 100.0}, current_equity=10_000.0)

    assert result is not None
    assert result.combined["AAPL"].signal == 0.10


def test_check_auto_resets_on_new_trading_day():
    from trading.impl.risk_guard.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=9_000.0)   # day 1 open

    # Day 2 — new timestamp date triggers auto-reset
    event = _bundle({"AAPL": 0.2}, ts=datetime(2024, 1, 3, 16, 5))
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=9_000.0)

    # Should NOT be None — day was reset with 9000 as new baseline
    assert result is not None


def test_reset_day_updates_baseline():
    from trading.impl.risk_guard.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=8_000.0)

    event = _bundle({"AAPL": 0.2})
    # 6% drop from 8000 = 7520 — breaches limit
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=7_520.0)
    assert result is None
