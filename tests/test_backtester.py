import queue
from datetime import datetime
from unittest.mock import MagicMock

from trading.backtester import Backtester
from trading.events import (
    BarBundleEvent, FillEvent, OrderEvent, SignalBundleEvent, SignalEvent, TickEvent,
)


def _bar_bundle() -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={"AAPL": TickEvent(symbol="AAPL", timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.0, volume=1000.0)},
    )


def _stopped_data() -> MagicMock:
    data = MagicMock()
    data.update_bars.return_value = False
    return data


def test_bar_bundle_routes_to_strategy():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    bundle = _bar_bundle()
    events.put(bundle)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    strategy.get_signals.assert_called_once_with(bundle)


def test_signal_bundle_routes_to_portfolio():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    sig = SignalEvent(symbol="AAPL", timestamp=datetime(2020, 1, 2), signal=1.0)
    bundle = SignalBundleEvent(timestamp=datetime(2020, 1, 2), signals={"AAPL": sig})
    events.put(bundle)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    portfolio.on_signal.assert_called_once_with(bundle)


def test_order_routes_to_execution():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10, reference_price=100.0,
    )
    events.put(order)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    execution.execute_order.assert_called_once_with(order)


def test_fill_routes_to_portfolio():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    fill = FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        direction="BUY", quantity=10, fill_price=100.5, commission=1.0,
    )
    events.put(fill)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    portfolio.on_fill.assert_called_once_with(fill)
