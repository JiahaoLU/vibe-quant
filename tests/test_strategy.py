import queue
from datetime import datetime
from trading.base.strategy import Strategy
from trading.impl.strategy import SMACrossoverStrategy
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


def _bars(closes: list[float]) -> list[TickEvent]:
    return [TickEvent(symbol="", timestamp=datetime(2020, 1, 2), open=c, high=c, low=c, close=c, volume=1000.0) for c in closes]


def _bundle(symbols: list[str], close: float = 100.0) -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={s: TickEvent(symbol=s, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000.0)
              for s in symbols},
    )


def test_strategy_abc_exposes_get_bars():
    """get_bars on the ABC should delegate to the callable passed at construction."""
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> None:
            pass

    stub = _Stub(get_bars=lambda s, n: [tick])
    assert stub.get_bars("AAPL", 1) == [tick]


def test_get_signals_emits_when_calculate_signals_returns_bundle():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)
    bundle = _bundle(["AAPL"])
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG")
    result = SignalBundleEvent(timestamp=ts, signals={"AAPL": sig})

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return result

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(bundle)
    assert collected == [result]


def test_get_signals_does_not_emit_when_calculate_signals_returns_none():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_no_signal_before_enough_history():
    events = queue.Queue()
    bars = _bars([100.0] * 5)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))
    assert events.empty()


def test_long_signal_when_fast_above_slow():
    events = queue.Queue()
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert not events.empty()
    bundle = events.get_nowait()
    assert isinstance(bundle, SignalBundleEvent)
    assert bundle.signals["AAPL"].signal_type == "LONG"


def test_no_duplicate_long_signal():
    events = queue.Queue()
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    events.get_nowait()
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert events.empty()


def test_exit_signal_when_fast_below_slow():
    # First trigger LONG: slow_sma=(20*90+10*110)/30=96.67, fast_sma=110 → LONG
    # Then flip: slow_sma=(20*110+10*90)/30=103.33, fast_sma=90 → EXIT
    events = queue.Queue()
    current_bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: current_bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    events.get_nowait()  # consume LONG

    current_bars = _bars([110.0] * 20 + [90.0] * 10)
    strategy.calculate_signals(_bundle(["AAPL"], close=90.0))
    bundle = events.get_nowait()
    assert bundle.signals["AAPL"].signal_type == "EXIT"


def test_no_signal_when_flat():
    events = queue.Queue()
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))
    assert events.empty()


def test_multi_symbol_signals_are_independent():
    events = queue.Queue()
    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)
        return _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL", "MSFT"], get_bars=get_bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    bundle = events.get_nowait()
    assert "AAPL" in bundle.signals
    assert "MSFT" not in bundle.signals


def test_no_emission_when_no_symbol_signals():
    events = queue.Queue()
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL", "MSFT"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    assert events.empty()
