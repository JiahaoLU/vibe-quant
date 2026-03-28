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
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    stub = _Stub(emit=lambda e: None, get_bars=lambda s, n: [tick])
    assert stub.get_bars("AAPL", 1) == [tick]


def test_get_signals_emits_when_calculate_signals_returns_bundle():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG")
    result = SignalBundleEvent(timestamp=ts, signals={"AAPL": sig})

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return result

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(_bundle(["AAPL"]))
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
    collected = []
    bars = _bars([100.0] * 5)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_long_signal_when_fast_above_slow():
    collected = []
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1
    assert isinstance(collected[0], SignalBundleEvent)
    assert collected[0].signals["AAPL"].signal_type == "LONG"


def test_no_duplicate_long_signal():
    collected = []
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1  # no second emit


def test_exit_signal_when_fast_below_slow():
    collected = []
    current_bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: current_bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert collected[-1].signals["AAPL"].signal_type == "LONG"

    current_bars = _bars([110.0] * 20 + [90.0] * 10)
    strategy.get_signals(_bundle(["AAPL"], close=90.0))
    assert collected[-1].signals["AAPL"].signal_type == "EXIT"


def test_no_signal_when_flat():
    collected = []
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_multi_symbol_signals_are_independent():
    collected = []
    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)
        return _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL", "MSFT"], get_bars=get_bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 1
    assert "AAPL" in collected[0].signals
    assert "MSFT" not in collected[0].signals


def test_no_emission_when_no_symbol_signals():
    collected = []
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL", "MSFT"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL", "MSFT"]))
    assert collected == []
