from datetime import datetime
from unittest.mock import MagicMock

from trading.events import SignalEvent, StrategyBundleEvent, TickEvent


def _get_bars(prices: dict[str, float]):
    def get_bars(symbol, n=1):
        p = prices.get(symbol, 100.0)
        return [TickEvent(symbol=symbol, timestamp=datetime(2024, 1, 2),
                          open=p, high=p, low=p, close=p, volume=1000.0)]
    return get_bars


def _bundle(symbol: str, signal: float) -> StrategyBundleEvent:
    ts = datetime(2024, 1, 2, 16, 5)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal=signal)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={symbol: sig},
        per_strategy={"s1": {symbol: 1.0}},
    )


def test_restore_sets_holdings_and_cash():
    from trading.impl.portfolio.simple_portfolio import SimplePortfolio

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
    )
    portfolio.restore(holdings={"AAPL": 10}, cash=8_500.0)

    assert portfolio._holdings["AAPL"] == 10
    assert portfolio._cash == 8_500.0


def test_on_signal_drops_signal_when_risk_guard_returns_none():
    from trading.impl.portfolio.simple_portfolio import SimplePortfolio

    mock_guard = MagicMock()
    mock_guard.check.return_value = None  # guard halts trading

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
        risk_guard=mock_guard,
    )
    portfolio.on_signal(_bundle("AAPL", 0.5))

    assert portfolio._pending_signals is None


def test_on_signal_uses_modified_event_from_risk_guard():
    from trading.impl.portfolio.simple_portfolio import SimplePortfolio
    from trading.events import SignalEvent, StrategyBundleEvent

    ts = datetime(2024, 1, 2, 16, 5)
    clamped_sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=0.1)
    clamped_bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": clamped_sig},
        per_strategy={"s1": {"AAPL": 1.0}},
    )
    mock_guard = MagicMock()
    mock_guard.check.return_value = clamped_bundle

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
        risk_guard=mock_guard,
    )
    portfolio.on_signal(_bundle("AAPL", 0.5))

    assert portfolio._pending_signals is not None
    assert portfolio._pending_signals.combined["AAPL"].signal == 0.1


def test_on_signal_without_risk_guard_stores_pending_signals():
    from trading.impl.portfolio.simple_portfolio import SimplePortfolio

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
    )
    bundle = _bundle("AAPL", 0.5)
    portfolio.on_signal(bundle)

    assert portfolio._pending_signals is bundle
