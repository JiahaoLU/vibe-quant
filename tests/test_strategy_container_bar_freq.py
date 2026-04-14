# tests/test_strategy_container_bar_freq.py
import pytest
from trading.base.strategy import Strategy
from trading.base.strategy_params import StrategyParams
from trading.impl.strategy_signal_generator.strategy_container import StrategyContainer


class _Stub(Strategy):
    def _init(self, p): pass
    def calculate_signals(self, event): return None


def _make_container():
    return StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])


def test_strategy_params_bar_freq_defaults_to_1d():
    p = StrategyParams(symbols=["AAPL"], name="test")
    assert p.bar_freq == "1d"


def test_strategy_params_bar_freq_can_be_set():
    p = StrategyParams(symbols=["AAPL"], name="test", bar_freq="5m")
    assert p.bar_freq == "5m"


def test_required_freq_returns_1d_when_no_strategies():
    container = _make_container()
    assert container.required_freq == "1d"


def test_required_freq_returns_1d_when_all_strategies_are_daily():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="1d"))
    assert container.required_freq == "1d"


def test_required_freq_returns_finest_intraday_freq():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="5m"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="1m"))
    assert container.required_freq == "1m"


def test_required_freq_raises_when_mixing_daily_and_intraday():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    with pytest.raises(ValueError, match="Cannot mix"):
        _ = container.required_freq


from datetime import datetime
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


def _bundle(symbols: list[str]) -> BarBundleEvent:
    ts = datetime(2024, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={
            s: TickEvent(symbol=s, timestamp=ts,
                         open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
            for s in symbols
        },
    )


def test_same_freq_strategy_fired_on_every_bar():
    """A '1m' strategy in a '1m' container fires on every bar."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(event.timestamp)
            return None

    container = _make_container()
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="s", bar_freq="1m"))
    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 5


def test_coarser_strategy_skipped_until_N_bars_elapsed():
    """A '5m' strategy in a '1m' container fires only once every 5 bars."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(event.timestamp)
            return None

    container = _make_container()
    # Register the 1m strategy first so required_freq resolves to "1m"
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))
    for _ in range(10):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 2   # fires on bar 5 and bar 10


def test_coarser_strategy_carry_forward_used_between_fires():
    """Between fires, the coarser strategy's last signal is carried forward."""
    emitted = []

    class _LongOnFire(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            return SignalBundleEvent(
                timestamp=event.timestamp,
                signals={"AAPL": SignalEvent(symbol="AAPL", timestamp=event.timestamp, signal=1.0)},
            )

    container = StrategyContainer(emit=emitted.append, get_bars=lambda s, n: [])
    # Add a 1m base so required_freq="1m"; 5m fires every 5 bars
    container.add(_Stub,      StrategyParams(symbols=["AAPL"], name="base",  bar_freq="1m"))
    container.add(_LongOnFire, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))

    # After 5 bars the 5m strategy fires and emits a StrategyBundleEvent
    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))
    assert len(emitted) == 1

    # Bar 6-9: carry-forward keeps the signal active even though _LongOnFire is not called
    for _ in range(4):
        container.get_signals(_bundle(["AAPL"]))
    # No new bundle emitted (no *new* signal from the 5m strategy between fires)
    assert len(emitted) == 1


def test_daily_strategies_fire_on_every_bar():
    """All '1d' strategies (the default) fire on every bar — no behaviour change."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(1)
            return None

    container = _make_container()
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="d", bar_freq="1d"))
    for _ in range(3):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 3
