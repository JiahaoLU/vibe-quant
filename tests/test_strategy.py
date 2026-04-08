from datetime import datetime
from trading.base.strategy import Strategy
from trading.base.strategy_params import StrategyParams
from strategies.sma_crossover_strategy import SMACrossoverStrategy, SMACrossoverStrategyParams
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
        def _init(self, strategy_params): pass
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    stub = _Stub(get_bars=lambda s, n: [tick], strategy_params=StrategyParams(symbols=["AAPL"], name="stub"))
    assert stub.get_bars("AAPL", 1) == [tick]


def test_on_get_signal_default_is_noop():
    """Default on_get_signal implementation does nothing and accepts None."""
    class _Stub(Strategy):
        def _init(self, strategy_params): pass
        def calculate_signals(self, event): return None

    stub = _Stub(get_bars=lambda s, n: [], strategy_params=StrategyParams(symbols=["AAPL"], name="stub"))
    stub.on_get_signal(None)   # must not raise
    ts = datetime(2020, 1, 2)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)
    bundle = SignalBundleEvent(timestamp=ts, signals={"AAPL": sig})
    stub.on_get_signal(bundle)  # must not raise


def test_no_signal_before_enough_history():
    bars = _bars([100.0] * 5)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30),
    )
    result = strategy.calculate_signals(_bundle(["AAPL"]))
    assert result is None


def test_long_signal_when_fast_above_slow():
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30),
    )
    result = strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert result is not None
    assert isinstance(result, SignalBundleEvent)
    assert result.signals["AAPL"].signal > 0.0


def test_no_duplicate_long_signal():
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30),
    )
    result1 = strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert result1 is not None
    result2 = strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert result2 is None  # no second emit on unchanged position


def test_exit_signal_when_fast_below_slow():
    current_bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: current_bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30),
    )
    result1 = strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert result1 is not None
    assert result1.signals["AAPL"].signal > 0.0

    current_bars = _bars([110.0] * 20 + [90.0] * 10)
    result2 = strategy.calculate_signals(_bundle(["AAPL"], close=90.0))
    assert result2 is not None
    assert result2.signals["AAPL"].signal == 0.0


def test_no_signal_when_flat():
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30),
    )
    result = strategy.calculate_signals(_bundle(["AAPL"]))
    assert result is None


def test_multi_symbol_signals_are_independent():
    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)
        return _bars([100.0] * 30)

    strategy = SMACrossoverStrategy(
        get_bars=get_bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL", "MSFT"], name="test_sma", fast=10, slow=30),
    )
    result = strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    assert result is not None
    assert result.signals["AAPL"].signal > 0.0
    assert result.signals["MSFT"].signal == 0.0


def test_no_emission_when_no_symbol_signals():
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(
        get_bars=lambda s, n: bars,
        strategy_params=SMACrossoverStrategyParams(symbols=["AAPL", "MSFT"], name="test_sma", fast=10, slow=30),
    )
    result = strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    assert result is None


def test_strategy_is_subclass_of_strategy_base():
    from trading.base.strategy import StrategyBase
    assert issubclass(Strategy, StrategyBase)


def test_strategy_is_abstract():
    """Strategy cannot be instantiated without implementing calculate_signals and _init."""
    import pytest

    class _NoImpl(Strategy):
        pass

    with pytest.raises(TypeError, match="Can't instantiate abstract class"):
        _NoImpl(get_bars=lambda s, n: [], strategy_params=StrategyParams(symbols=[], name="abstract"))
