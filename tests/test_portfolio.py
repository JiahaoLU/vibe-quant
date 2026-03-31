from datetime import datetime

from trading.impl.simple_portfolio import SimplePortfolio
from trading.events import BarBundleEvent, FillEvent, OrderEvent, SignalBundleEvent, SignalEvent, TickEvent


def _get_bars(prices: dict[str, float]):
    def get_bars(symbol, n=1):
        p = prices[symbol]
        return [TickEvent(symbol=symbol, timestamp=datetime(2020, 1, 2), open=p, high=p, low=p, close=p, volume=1000.0)]
    return get_bars


def _signal_bundle(symbol: str, signal: float, ts=None) -> SignalBundleEvent:
    ts = ts or datetime(2020, 1, 2)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal=signal)
    return SignalBundleEvent(timestamp=ts, signals={symbol: sig})


def _fill(symbol: str, direction: str, quantity: int, price: float) -> FillEvent:
    return FillEvent(
        symbol=symbol, timestamp=datetime(2020, 1, 2),
        direction=direction, quantity=quantity,
        fill_price=price, commission=1.0,
    )


def _fill_bar(symbol: str, open_price: float, ts=None):
    ts = ts or datetime(2020, 1, 3)
    tick = TickEvent(symbol=symbol, timestamp=ts,
                     open=open_price, high=open_price, low=open_price, close=open_price, volume=1000.0)
    return BarBundleEvent(timestamp=ts, bars={symbol: tick})


def test_portfolio_constructor_accepts_emit_callable():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    assert portfolio is not None


def test_long_signal_emits_buy_order():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    order = collected[0]
    assert isinstance(order, OrderEvent)
    assert order.symbol == "AAPL"
    assert order.direction == "BUY"
    assert order.quantity == 100   # int(1.0 * 10_000 / 100)
    assert order.reference_price == 100.0


def test_long_signal_topup_when_partial_holdings():
    """A signal with weight 1.0 tops up to the full target even when already holding."""
    from trading.events import FillEvent as _FE
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    # Use commission=0 so cash arithmetic is exact: cash after buy = 10000 − 50*100 = 5000
    portfolio.on_fill(_FE(symbol="AAPL", timestamp=datetime(2020, 1, 2),
                          direction="BUY", quantity=50, fill_price=100.0, commission=0.0))
    collected.clear()

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    # target = int(1.0 * 10_000 / 100) = 100; held = 50; delta = 50; cost = 5000 ≤ cash 5000
    assert len(collected) == 1
    assert collected[0].direction == "BUY"
    assert collected[0].quantity == 50   # target 100 − held 50


def test_exit_signal_emits_sell_order():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_signal_bundle("AAPL", 0.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "SELL"
    assert collected[0].quantity == 50


def test_exit_signal_no_order_when_no_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", 0.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert collected == []


def test_short_signal_treated_as_exit():
    """Negative signal (short) is clamped to 0 — no short positions allowed."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_signal_bundle("AAPL", -0.5))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "SELL"
    assert collected[0].quantity == 50   # closes position, does not go short


def test_short_signal_no_order_when_flat():
    """Negative signal with no holdings → still no order (clamped to 0 = exit with nothing to sell)."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", -1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert collected == []


def test_on_fill_updates_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 50


def test_on_fill_sell_decreases_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 0


def test_equity_sums_all_symbol_holdings():
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 200.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))
    snapshot = portfolio.equity_curve[-1]
    assert snapshot["market_value"] == 1000.0
    assert snapshot["holdings"] == {"AAPL": 10, "MSFT": 0}


def test_long_signal_no_order_when_no_cash():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=50.0)

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    # target = int(1.0 * 50 / 100) = 0 → delta = 0 → no order
    assert collected == []


def test_multi_symbol_normalised_signals_do_not_overdraw_cash():
    """Equal-weight signals (0.5 each) for 2 symbols should fit within initial_capital."""
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = SignalBundleEvent(
        timestamp=ts,
        signals={
            "AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=0.5),
            "MSFT": SignalEvent(symbol="MSFT", timestamp=ts, signal=0.5),
        },
    )
    portfolio.on_signal(bundle)

    fill_ts = datetime(2020, 1, 3)
    fill_bar = BarBundleEvent(
        timestamp=fill_ts,
        bars={
            "AAPL": TickEvent(symbol="AAPL", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
            "MSFT": TickEvent(symbol="MSFT", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
        },
    )
    portfolio.fill_pending_orders(fill_bar)

    total_order_value = sum(o.quantity * o.reference_price for o in collected)
    assert total_order_value <= 10_000.0, f"Orders exceed cash: {total_order_value}"


def test_fill_pending_orders_uses_open_price():
    """fill_pending_orders uses the fill bar's open price, not the signal bar's close."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))  # signal at close=100

    fill_ts = datetime(2020, 1, 3)
    fill_bar = BarBundleEvent(
        timestamp=fill_ts,
        bars={"AAPL": TickEvent(symbol="AAPL", timestamp=fill_ts,
                                open=105.0, high=106.0, low=104.0, close=105.5, volume=1000.0)},
    )
    portfolio.fill_pending_orders(fill_bar)

    assert len(collected) == 1
    assert collected[0].reference_price == 105.0   # open of fill bar, not 100.0


def test_fill_pending_orders_no_op_before_any_signal():
    """fill_pending_orders before any on_signal emits nothing."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert collected == []


def test_pending_signals_cleared_after_fill():
    """A second fill_pending_orders call after the first emits nothing."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))  # emits order
    collected.clear()

    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))  # pending was cleared

    assert collected == []


def test_on_signal_does_not_emit_orders_directly():
    """on_signal stores pending only — calling it without fill_pending_orders emits nothing."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", 1.0))

    assert collected == []
