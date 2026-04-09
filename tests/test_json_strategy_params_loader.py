import json
from pathlib import Path

import pytest

from strategies.sma_crossover_strategy import SMACrossoverStrategy, SMACrossoverStrategyParams
from trading.base.strategy_params import StrategyParams
from trading.base.strategy_params_loader import StrategyParamsLoader
from trading.impl.strategy_params_loader.json_strategy_params_loader import JsonStrategyParamsLoader


def test_strategy_params_loader_is_abstract():
    with pytest.raises(TypeError):
        StrategyParamsLoader()


class _ConcreteLoader(StrategyParamsLoader):
    def load(self, strategy_name: str) -> StrategyParams:
        return StrategyParams(symbols=["AAPL"], name=strategy_name)

    def load_all(self):
        return []


def test_concrete_subclass_is_instantiable():
    loader = _ConcreteLoader()
    result = loader.load("my_strategy")
    assert isinstance(result, StrategyParams)
    assert result.name == "my_strategy"


def test_concrete_load_all_returns_list():
    assert _ConcreteLoader().load_all() == []


@pytest.fixture
def params_dir(tmp_path: Path) -> Path:
    return tmp_path


def _setup_dir(params_dir: Path, registry: dict[str, str], strategies: dict[str, dict]) -> None:
    (params_dir / "params.json").write_text(json.dumps(registry))
    for name, data in strategies.items():
        (params_dir / f"{name}.json").write_text(json.dumps(data))


def test_load_injects_strategy_name(params_dir: Path):
    _setup_dir(
        params_dir,
        registry={"sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"},
        strategies={"sma_10_30": {"symbols": ["AAPL"], "fast": 10, "slow": 30, "nominal": 1.0}},
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    result = loader.load("sma_10_30")
    assert isinstance(result, SMACrossoverStrategyParams)
    assert result.name == "sma_10_30"
    assert result.fast == 10
    assert result.slow == 30


def test_load_all_returns_strategy_class_and_params(params_dir: Path):
    _setup_dir(
        params_dir,
        registry={"sma_fast": "strategies.sma_crossover_strategy.SMACrossoverStrategy"},
        strategies={"sma_fast": {"symbols": ["MSFT"], "fast": 5, "slow": 20, "nominal": 0.5}},
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    all_strategies = loader.load_all()
    assert len(all_strategies) == 1
    strategy_cls, params = all_strategies[0]
    assert strategy_cls is SMACrossoverStrategy
    assert isinstance(params, SMACrossoverStrategyParams)
    assert params.name == "sma_fast"
    assert params.symbols == ["MSFT"]


def test_two_strategies_same_class(params_dir: Path):
    _setup_dir(
        params_dir,
        registry={
            "sma_a": "strategies.sma_crossover_strategy.SMACrossoverStrategy",
            "sma_b": "strategies.sma_crossover_strategy.SMACrossoverStrategy",
        },
        strategies={
            "sma_a": {"symbols": ["AAPL"], "fast": 5, "slow": 15, "nominal": 1.0},
            "sma_b": {"symbols": ["MSFT"], "fast": 20, "slow": 60, "nominal": 1.0},
        },
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    all_strategies = loader.load_all()
    assert len(all_strategies) == 2
    names = {params.name for _, params in all_strategies}
    assert names == {"sma_a", "sma_b"}


def test_load_missing_file_raises(params_dir: Path):
    (params_dir / "params.json").write_text(json.dumps(
        {"sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"}
    ))
    loader = JsonStrategyParamsLoader(str(params_dir))
    with pytest.raises(FileNotFoundError):
        loader.load("sma_10_30")


def test_load_unknown_strategy_raises(params_dir: Path):
    (params_dir / "params.json").write_text(json.dumps({}))
    loader = JsonStrategyParamsLoader(str(params_dir))
    with pytest.raises(KeyError):
        loader.load("nonexistent")


def test_missing_params_json_raises(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        JsonStrategyParamsLoader(str(tmp_path))


def test_load_name_in_json_is_overridden_by_registry_key(params_dir: Path):
    # Even if someone accidentally puts "name" in the JSON, the registry key wins.
    _setup_dir(
        params_dir,
        registry={"sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"},
        strategies={"sma_10_30": {"symbols": ["AAPL"], "fast": 10, "slow": 30, "name": "wrong"}},
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    result = loader.load("sma_10_30")
    assert result.name == "sma_10_30"
