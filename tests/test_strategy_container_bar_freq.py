# tests/test_strategy_container_bar_freq.py
from trading.base.strategy_params import StrategyParams


def test_strategy_params_bar_freq_defaults_to_1d():
    p = StrategyParams(symbols=["AAPL"], name="test")
    assert p.bar_freq == "1d"


def test_strategy_params_bar_freq_can_be_set():
    p = StrategyParams(symbols=["AAPL"], name="test", bar_freq="5m")
    assert p.bar_freq == "5m"


from trading.base.strategy import Strategy
from trading.impl.strategy_signal_generator.strategy_container import StrategyContainer


class _Stub(Strategy):
    def _init(self, p): pass
    def calculate_signals(self, event): return None


def _make_container():
    return StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])


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
    import pytest
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    with pytest.raises(ValueError, match="Cannot mix"):
        _ = container.required_freq
