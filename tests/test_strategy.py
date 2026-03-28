import queue
from datetime import datetime
from unittest.mock import MagicMock

from trading.impl.strategy import SMACrossoverStrategy
from trading.events import BarBundleEvent, SignalBundleEvent, TickEvent


def _bars(closes: list[float]) -> list[TickEvent]:
    return [TickEvent(symbol="", timestamp=datetime(2020, 1, 2), open=c, high=c, low=c, close=c, volume=1000.0) for c in closes]


def _bundle(symbols: list[str], close: float = 100.0) -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={s: TickEvent(symbol=s, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000.0)
              for s in symbols},
    )


def test_no_signal_before_enough_history():
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([100.0] * 5)  # only 5, need 30

    strategy = SMACrossoverStrategy(events, data, ["AAPL"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))

    assert events.empty()


def test_long_signal_when_fast_above_slow():
    # slow_sma = (20*90 + 10*110)/30 = 96.67, fast_sma = 110 → LONG
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([90.0] * 20 + [110.0] * 10)

    strategy = SMACrossoverStrategy(events, data, ["AAPL"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))

    assert not events.empty()
    bundle = events.get_nowait()
    assert isinstance(bundle, SignalBundleEvent)
    assert bundle.signals["AAPL"].signal_type == "LONG"


def test_no_duplicate_long_signal():
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([90.0] * 20 + [110.0] * 10)

    strategy = SMACrossoverStrategy(events, data, ["AAPL"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))  # first call → LONG
    events.get_nowait()
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))  # still fast > slow, already LONG

    assert events.empty()


def test_exit_signal_when_fast_below_slow():
    # First trigger LONG, then flip: slow_sma=(20*110+10*90)/30=103.33, fast_sma=90 → EXIT
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([90.0] * 20 + [110.0] * 10)

    strategy = SMACrossoverStrategy(events, data, ["AAPL"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    events.get_nowait()  # consume LONG

    data.get_latest_bars.return_value = _bars([110.0] * 20 + [90.0] * 10)
    strategy.calculate_signals(_bundle(["AAPL"], close=90.0))

    bundle = events.get_nowait()
    assert bundle.signals["AAPL"].signal_type == "EXIT"


def test_no_signal_when_flat():
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([100.0] * 30)  # fast==slow, no crossover

    strategy = SMACrossoverStrategy(events, data, ["AAPL"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))

    assert events.empty()


def test_multi_symbol_signals_are_independent():
    events = queue.Queue()
    data = MagicMock()

    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)   # LONG crossover
        return _bars([100.0] * 30)                       # MSFT flat — no signal

    data.get_latest_bars.side_effect = get_bars

    strategy = SMACrossoverStrategy(events, data, ["AAPL", "MSFT"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))

    bundle = events.get_nowait()
    assert "AAPL" in bundle.signals
    assert "MSFT" not in bundle.signals


def test_no_emission_when_no_symbol_signals():
    events = queue.Queue()
    data = MagicMock()
    data.get_latest_bars.return_value = _bars([100.0] * 30)

    strategy = SMACrossoverStrategy(events, data, ["AAPL", "MSFT"], fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))

    assert events.empty()
