from datetime import datetime
from trading.base.strategy import Strategy, StrategyBase
from trading.base.strategy_params import StrategyParams
from trading.impl.strategy_container import StrategyContainer
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


def _bundle(symbols: list[str], close: float = 100.0) -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={s: TickEvent(symbol=s, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000.0)
              for s in symbols},
    )


class _AlwaysLong(Strategy):
    """Stub that always returns a full-weight long signal for every symbol."""
    def _init(self, strategy_params: StrategyParams):
        pass

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        ts = event.timestamp
        if self.symbols:
            self.get_bars(self.symbols[0], 1)
        n = len(self.symbols) or 1
        signals = {s: SignalEvent(symbol=s, timestamp=ts, signal=1.0 / n) for s in self.symbols}
        return SignalBundleEvent(timestamp=ts, signals=signals)


class _NeverSignals(Strategy):
    """Stub that always returns None."""
    def _init(self, strategy_params: StrategyParams):
        pass

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        return None


def test_container_is_subclass_of_strategy_base():
    assert issubclass(StrategyContainer, StrategyBase)


def test_add_factory_emits_one_combined_bundle():
    """Container aggregates strategy results and emits exactly one SignalBundleEvent."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    assert isinstance(collected[0], SignalBundleEvent)


def test_add_factory_respects_overridden_get_bars():
    """Factory add uses a custom get_bars kwarg, not the container default."""
    default_calls = []
    custom_calls = []
    container = StrategyContainer(
        emit=lambda e: None,
        get_bars=lambda s, n: default_calls.append(s) or [],
    )
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]), get_bars=lambda s, n: custom_calls.append(s) or [])
    container.get_signals(_bundle(["AAPL"]))
    assert "AAPL" in custom_calls
    assert default_calls == []


def test_add_strategy_accepts_prebuilt_instance():
    """add_strategy registers a pre-constructed instance; its signals flow through the container."""
    container_emit = []
    strategy = _AlwaysLong(
        emit=lambda e: None,
        get_bars=lambda s, n: [],
        strategy_params=StrategyParams(symbols=["AAPL"]),
    )
    container = StrategyContainer(emit=container_emit.append, get_bars=lambda s, n: [])
    container.add_strategy(strategy)
    container.get_signals(_bundle(["AAPL"]))
    assert len(container_emit) == 1
    assert isinstance(container_emit[0], SignalBundleEvent)


def test_get_signals_combines_independent_symbol_strategies():
    """Two strategies for different symbols produce one combined bundle covering both."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.add(_AlwaysLong, StrategyParams(symbols=["MSFT"]))
    container.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 1
    bundle = collected[0]
    assert "AAPL" in bundle.signals
    assert "MSFT" in bundle.signals


def test_strategy_returning_none_emits_nothing():
    """A container of only None-returning strategies emits nothing."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_NeverSignals, StrategyParams(symbols=[]))
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_empty_container_emits_nothing():
    """An empty container does not crash and emits nothing."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_two_strategies_same_symbol_weighted_by_nominal():
    """Two strategies targeting the same symbol emit one combined bundle with weighted signal."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    # Strategy A: nominal 3, signal 1.0 → contribution 3/5 * 1.0 = 0.6
    # Strategy B: nominal 2, signal 1.0 → contribution 2/5 * 1.0 = 0.4
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=3.0))
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=2.0))
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    combined_signal = collected[0].signals["AAPL"].signal
    assert abs(combined_signal - 1.0) < 1e-9   # both long → weighted avg = 1.0


def test_carry_forward_applies_when_one_strategy_silent():
    """If strategy B fired last bar but not this bar, its last signal still contributes."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=1.0))
    container.add(_NeverSignals, StrategyParams(symbols=[], nominal=1.0))

    # Bar 1: only _AlwaysLong fires
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1

    # Bar 2: still only _AlwaysLong fires → combined bundle still emitted
    collected.clear()
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1


def test_nominal_weights_combined_signal():
    """Strategy with double the nominal contributes proportionally more to the combined signal."""

    class _HalfSignal(Strategy):
        """Returns signal=0.5 for its symbol."""
        def _init(self, p): pass
        def calculate_signals(self, event):
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={s: SignalEvent(symbol=s, timestamp=ts, signal=0.5) for s in self.symbols},
            )

    class _FullSignal(Strategy):
        """Returns signal=1.0 for its symbol."""
        def _init(self, p): pass
        def calculate_signals(self, event):
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={s: SignalEvent(symbol=s, timestamp=ts, signal=1.0) for s in self.symbols},
            )

    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    # nominal 1 with signal 0.5, nominal 1 with signal 1.0 → weighted avg = 0.75
    container.add(_HalfSignal, StrategyParams(symbols=["AAPL"], nominal=1.0))
    container.add(_FullSignal, StrategyParams(symbols=["AAPL"], nominal=1.0))
    container.get_signals(_bundle(["AAPL"]))

    assert len(collected) == 1
    assert abs(collected[0].signals["AAPL"].signal - 0.75) < 1e-9
