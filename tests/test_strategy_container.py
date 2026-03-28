from datetime import datetime
from trading.base.strategy import Strategy, StrategyBase
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
    """Stub that always returns a LONG signal for every symbol."""
    def __init__(self, emit, symbols, get_bars):
        super().__init__(emit, get_bars)
        self._symbols = symbols

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        ts = event.timestamp
        # Use get_bars to ensure the injected callback is actually called
        self.get_bars(self._symbols[0], 1) if self._symbols else None
        signals = {s: SignalEvent(symbol=s, timestamp=ts, signal_type="LONG") for s in self._symbols}
        return SignalBundleEvent(timestamp=ts, signals=signals)


class _NeverSignals(Strategy):
    """Stub that always returns None."""
    def __init__(self, emit, get_bars):
        super().__init__(emit, get_bars)

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        return None


def test_container_is_subclass_of_strategy_base():
    assert issubclass(StrategyContainer, StrategyBase)


def test_add_factory_injects_default_emit_and_get_bars():
    """Factory add injects container's emit and get_bars when not in kwargs."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    assert isinstance(collected[0], SignalBundleEvent)


def test_add_factory_respects_overridden_emit():
    """Factory add uses a custom emit kwarg, not the container default."""
    default_collected = []
    custom_collected = []
    container = StrategyContainer(emit=default_collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"], emit=custom_collected.append)
    container.get_signals(_bundle(["AAPL"]))
    assert len(custom_collected) == 1
    assert default_collected == []


def test_add_factory_respects_overridden_get_bars():
    """Factory add uses a custom get_bars kwarg, not the container default."""
    default_calls = []
    custom_calls = []
    container = StrategyContainer(
        emit=lambda e: None,
        get_bars=lambda s, n: default_calls.append(s) or [],
    )
    container.add(_AlwaysLong, symbols=["AAPL"], get_bars=lambda s, n: custom_calls.append(s) or [])
    container.get_signals(_bundle(["AAPL"]))
    assert "AAPL" in custom_calls
    assert default_calls == []


def test_add_strategy_accepts_prebuilt_instance():
    """add_strategy adds a pre-constructed instance and dispatches to it."""
    collected = []
    strategy = _AlwaysLong(emit=collected.append, symbols=["AAPL"], get_bars=lambda s, n: [])
    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])
    container.add_strategy(strategy)
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1


def test_get_signals_dispatches_to_all_strategies():
    """All contained strategies receive the bar bundle."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.add(_AlwaysLong, symbols=["MSFT"])
    container.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 2


def test_strategy_returning_none_emits_nothing():
    """A strategy returning None from calculate_signals does not emit."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_NeverSignals)
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_empty_container_emits_nothing():
    """An empty container does not crash and emits nothing."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_two_strategies_same_symbol_emit_independent_bundles():
    """Two strategies for the same symbol emit two separate SignalBundleEvents."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 2
    assert all(isinstance(e, SignalBundleEvent) for e in collected)
