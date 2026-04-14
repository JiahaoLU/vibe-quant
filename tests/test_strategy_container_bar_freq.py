# tests/test_strategy_container_bar_freq.py
import pytest
from datetime import datetime, timedelta
from trading.base.strategy import Strategy
from trading.base.strategy_params import StrategyParams
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent
from trading.impl.strategy_signal_generator.strategy_container import (
    StrategyContainer,
    _aggregate_bars,
)


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


def test_on_get_signal_not_called_when_strategy_skipped():
    """on_get_signal must not fire on bars where the strategy is gated out by demux."""
    hook_calls = []

    class _Tracking(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event): return None
        def on_get_signal(self, result):
            hook_calls.append(result)

    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add(_Tracking, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))
    for _ in range(4):  # bars 1-4: 5m strategy is gated
        container.get_signals(_bundle(["AAPL"]))
    assert hook_calls == []
    container.get_signals(_bundle(["AAPL"]))  # bar 5: fires
    assert len(hook_calls) == 1


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


# ---------------------------------------------------------------------------
# Helpers for adapter / aggregation tests
# ---------------------------------------------------------------------------

_BASE_TS = datetime(2024, 1, 2, 9, 30)


def _make_ticks(n: int, symbol: str = "AAPL") -> list[TickEvent]:
    """Make n TickEvents with distinct, predictable OHLCV values.

    open = i, high = i + 0.5, low = i - 0.5, close = i + 0.1, volume = 100 + i
    """
    return [
        TickEvent(
            symbol=symbol,
            timestamp=_BASE_TS + timedelta(minutes=i),
            open=float(i),
            high=float(i) + 0.5,
            low=float(i) - 0.5,
            close=float(i) + 0.1,
            volume=float(100 + i),
        )
        for i in range(n)
    ]


# ---------------------------------------------------------------------------
# _aggregate_bars — pure unit tests
# ---------------------------------------------------------------------------

def test_aggregate_bars_basic_ohlcv():
    """Steps=2, 4 bars → 2 groups; verify open/high/low/close/volume per group."""
    bars = _make_ticks(4)
    # bar 0: open=0, high=0.5, low=-0.5, close=0.1, vol=100
    # bar 1: open=1, high=1.5, low=0.5,  close=1.1, vol=101
    # bar 2: open=2, high=2.5, low=1.5,  close=2.1, vol=102
    # bar 3: open=3, high=3.5, low=2.5,  close=3.1, vol=103
    result = _aggregate_bars(bars, 2)
    assert len(result) == 2
    g0, g1 = result
    assert g0.open   == 0.0
    assert g0.high   == 1.5
    assert g0.low    == -0.5
    assert g0.close  == 1.1
    assert g0.volume == 201.0
    assert g1.open   == 2.0
    assert g1.high   == 3.5
    assert g1.low    == 1.5
    assert g1.close  == 3.1
    assert g1.volume == 205.0


def test_aggregate_bars_timestamp_is_last_bar_in_group():
    """Aggregated bar timestamp == last bar in the group."""
    bars = _make_ticks(4)
    result = _aggregate_bars(bars, 2)
    assert result[0].timestamp == bars[1].timestamp
    assert result[1].timestamp == bars[3].timestamp


def test_aggregate_bars_exact_fit():
    """6 bars at steps=3 → 2 groups, no leading partial bars."""
    bars = _make_ticks(6)
    result = _aggregate_bars(bars, 3)
    assert len(result) == 2


def test_aggregate_bars_discards_partial_leading_group():
    """7 bars at steps=3 → 2 groups (leading 1 bar discarded, not 3 groups)."""
    bars = _make_ticks(7)
    result = _aggregate_bars(bars, 3)
    assert len(result) == 2
    # First group must start at bars[1] (bars[0] is the discarded partial)
    assert result[0].open == bars[1].open


def test_aggregate_bars_empty_input():
    """Empty bar list → empty result."""
    assert _aggregate_bars([], 5) == []


def test_aggregate_bars_fewer_than_steps():
    """Fewer bars than steps → no complete group → empty result."""
    bars = _make_ticks(3)
    assert _aggregate_bars(bars, 5) == []


def test_aggregate_bars_is_synthetic_true_only_when_all_synthetic():
    """is_synthetic=True on aggregated bar only when every constituent bar is synthetic."""
    ts = _BASE_TS

    def _tick(synthetic: bool) -> TickEvent:
        return TickEvent(
            symbol="A", timestamp=ts,
            open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
            is_synthetic=synthetic,
        )

    all_synthetic = [_tick(True), _tick(True)]
    mixed         = [_tick(True), _tick(False)]
    none_synthetic = [_tick(False), _tick(False)]

    assert _aggregate_bars(all_synthetic,  2)[0].is_synthetic is True
    assert _aggregate_bars(mixed,          2)[0].is_synthetic is False
    assert _aggregate_bars(none_synthetic, 2)[0].is_synthetic is False


def test_aggregate_bars_is_delisted_from_last_bar():
    """is_delisted on aggregated bar is taken from the last bar in the group."""
    ts = _BASE_TS

    def _tick(delisted: bool) -> TickEvent:
        return TickEvent(
            symbol="A", timestamp=ts,
            open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0,
            is_delisted=delisted,
        )

    not_then_delisted = [_tick(False), _tick(True)]
    delisted_then_not = [_tick(True),  _tick(False)]

    assert _aggregate_bars(not_then_delisted, 2)[0].is_delisted is True
    assert _aggregate_bars(delisted_then_not, 2)[0].is_delisted is False


# ---------------------------------------------------------------------------
# Adapter integration — via add() (factory path)
# ---------------------------------------------------------------------------

def test_add_get_bars_passthrough_when_same_freq():
    """Steps=1: adapter is a no-op; strategy receives exactly n raw bars."""
    raw = _make_ticks(3)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 3))
            return None

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: raw[-n:])
    container.add(_Capture, StrategyParams(symbols=["AAPL"], name="c", bar_freq="1m"))
    container.get_signals(_bundle(["AAPL"]))

    assert len(received) == 3
    assert received == raw


def test_add_get_bars_returns_n_coarse_bars_for_coarser_strategy():
    """5m strategy (steps=5) asking for n=2 bars receives 2 aggregated bars, not 10 raw bars."""
    fine_bars = _make_ticks(10)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 2))
            return None

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: fine_bars[-n:])
    container.add(_Stub,    StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add(_Capture, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))

    # Advance to bar 5 so the 5m strategy fires
    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))

    assert len(received) == 2


def test_add_get_bars_aggregated_ohlcv_correct():
    """OHLCV values of the bars returned to a 5m strategy are correctly aggregated from 1m bars."""
    # Supply exactly 10 fine-grained bars (2 groups of 5)
    fine_bars = _make_ticks(10)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 2))
            return None

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: fine_bars[-n:])
    container.add(_Stub,    StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add(_Capture, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))

    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))

    expected = _aggregate_bars(fine_bars, 5)
    assert received == expected


def test_add_steps_correct_when_finer_strategy_registered_last():
    """Coarser strategy added first still receives correctly aggregated bars after finer strategy is registered.

    Regression: lazy self._steps[idx] lookup means the step is evaluated at call time,
    so required_freq finalises correctly regardless of registration order.
    """
    fine_bars = _make_ticks(10)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 2))
            return None

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: fine_bars[-n:])
    # Register coarser first, finer second — required_freq changes on second add
    container.add(_Capture, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))
    container.add(_Stub,    StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))

    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))

    assert len(received) == 2


# ---------------------------------------------------------------------------
# Adapter integration — via add_strategy() (pre-built instance path)
# ---------------------------------------------------------------------------

def test_add_strategy_wraps_get_bars_for_coarser_freq():
    """Pre-built 5m strategy registered via add_strategy() receives aggregated bars."""
    fine_bars = _make_ticks(10)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 2))
            return None

    # Pre-build with the raw get_bars; the container must wrap it
    strategy = _Capture(
        get_bars=lambda s, n: fine_bars[-n:],
        strategy_params=StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"),
    )

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: fine_bars[-n:])
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add_strategy(strategy)

    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))

    assert len(received) == 2


def test_add_strategy_same_freq_passthrough():
    """Pre-built same-freq strategy registered via add_strategy() receives raw bars unchanged."""
    raw = _make_ticks(3)
    received = []

    class _Capture(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            received.extend(self.get_bars("AAPL", 3))
            return None

    strategy = _Capture(
        get_bars=lambda s, n: raw[-n:],
        strategy_params=StrategyParams(symbols=["AAPL"], name="same", bar_freq="1m"),
    )

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: raw[-n:])
    container.add_strategy(strategy)

    container.get_signals(_bundle(["AAPL"]))

    assert len(received) == 3
    assert received == raw
