from datetime import datetime

from trading.events import (
    EventType, Event, BarBundleEvent, SignalEvent, SignalBundleEvent,
    OrderEvent, FillEvent, TickEvent,
)


def test_bar_bundle_event_type():
    ts = datetime(2020, 1, 2)
    e = BarBundleEvent(
        timestamp=ts,
        bars={"AAPL": TickEvent(symbol="AAPL", timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)},
    )
    assert e.type == EventType.BAR_BUNDLE


def test_signal_bundle_event_type():
    sig = SignalEvent(symbol="AAPL", timestamp=datetime(2020, 1, 2), signal_type="LONG")
    e = SignalBundleEvent(timestamp=datetime(2020, 1, 2), signals={"AAPL": sig})
    assert e.type == EventType.SIGNAL_BUNDLE


def test_signal_event_is_not_event_subclass():
    assert not issubclass(SignalEvent, Event)


def test_event_type_market_removed():
    assert not hasattr(EventType, "MARKET")


def test_event_type_signal_removed():
    assert not hasattr(EventType, "SIGNAL")


def test_order_event_type():
    e = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10, reference_price=100.0,
    )
    assert e.type == EventType.ORDER


def test_fill_event_type():
    e = FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        direction="BUY", quantity=10, fill_price=100.5, commission=1.0,
    )
    assert e.type == EventType.FILL
