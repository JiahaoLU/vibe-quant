import queue
from datetime import datetime
from unittest.mock import MagicMock

from trading.impl.portfolio import SimplePortfolio
from trading.events import FillEvent, OrderEvent, SignalBundleEvent, SignalEvent, TickEvent


def _data(prices: dict[str, float]) -> MagicMock:
    """Return a mock DataHandler whose get_latest_bars returns bars at the given prices."""
    data = MagicMock()
    def get_bars(symbol, n=1):
        p = prices[symbol]
        return [TickEvent(symbol=symbol, timestamp=datetime(2020, 1, 2), open=p, high=p, low=p, close=p, volume=1000.0)]
    data.get_latest_bars.side_effect = get_bars
    return data


def _signal_bundle(symbol: str, signal_type: str, ts=None) -> SignalBundleEvent:
    ts = ts or datetime(2020, 1, 2)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal_type=signal_type)
    return SignalBundleEvent(timestamp=ts, signals={symbol: sig})


def _fill(symbol: str, direction: str, quantity: int, price: float) -> FillEvent:
    return FillEvent(
        symbol=symbol, timestamp=datetime(2020, 1, 2),
        direction=direction, quantity=quantity,
        fill_price=price, commission=1.0,
    )


def test_long_signal_emits_buy_order():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))

    assert not events.empty()
    order = events.get_nowait()
    assert isinstance(order, OrderEvent)
    assert order.symbol == "AAPL"
    assert order.direction == "BUY"
    assert order.quantity == 100   # 10_000 // 100


def test_long_signal_no_order_when_already_holding():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    events.queue.clear()  # discard any queued events from fill side-effects

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))
    assert events.empty()


def test_exit_signal_emits_sell_order():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    events.queue.clear()

    portfolio.on_signal(_signal_bundle("AAPL", "EXIT"))

    order = events.get_nowait()
    assert order.direction == "SELL"
    assert order.quantity == 50


def test_exit_signal_no_order_when_no_holdings():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", "EXIT"))
    assert events.empty()


def test_on_fill_updates_holdings():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))

    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 50


def test_on_fill_sell_decreases_holdings():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 50, 100.0))

    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 0


def test_equity_sums_all_symbol_holdings():
    events = queue.Queue()
    prices = {"AAPL": 100.0, "MSFT": 200.0}
    portfolio = SimplePortfolio(events, _data(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))  # 10 shares @ 100
    snapshot = portfolio.equity_curve[-1]
    # AAPL: 10 * 100 = 1000, MSFT: 0 * 200 = 0
    assert snapshot["market_value"] == 1000.0
    assert snapshot["holdings"] == {"AAPL": 10, "MSFT": 0}


def test_long_signal_no_order_when_no_cash():
    events = queue.Queue()
    portfolio = SimplePortfolio(events, _data({"AAPL": 100.0}), ["AAPL"], initial_capital=50.0)
    # price=100, cash=50 → quantity = int(50 // 100) = 0, no order

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))
    assert events.empty()


def test_multi_symbol_long_does_not_overdraw_cash():
    """Two simultaneous LONG signals must not together exceed available cash."""
    events = queue.Queue()
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio = SimplePortfolio(events, _data(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    # Both symbols signal LONG at the same time
    ts = datetime(2020, 1, 2)
    bundle = SignalBundleEvent(
        timestamp=ts,
        signals={
            "AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG"),
            "MSFT": SignalEvent(symbol="MSFT", timestamp=ts, signal_type="LONG"),
        },
    )
    portfolio.on_signal(bundle)

    orders = []
    while not events.empty():
        orders.append(events.get_nowait())

    total_order_value = sum(o.quantity * o.reference_price for o in orders)
    assert total_order_value <= 10_000.0, f"Orders exceed cash: {total_order_value}"
