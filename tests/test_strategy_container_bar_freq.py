# tests/test_strategy_container_bar_freq.py
from trading.base.strategy_params import StrategyParams


def test_strategy_params_bar_freq_defaults_to_1d():
    p = StrategyParams(symbols=["AAPL"], name="test")
    assert p.bar_freq == "1d"


def test_strategy_params_bar_freq_can_be_set():
    p = StrategyParams(symbols=["AAPL"], name="test", bar_freq="5m")
    assert p.bar_freq == "5m"
