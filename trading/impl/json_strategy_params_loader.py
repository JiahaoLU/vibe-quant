import importlib
import json
from pathlib import Path

from trading.base.strategy_params import StrategyParams
from trading.base.strategy_params_loader import StrategyParamsLoader


class JsonStrategyParamsLoader(StrategyParamsLoader):
    """Load strategy classes and params from a JSON registry and per-strategy files."""

    def __init__(self, params_dir: str) -> None:
        self._params_dir = Path(params_dir)
        registry_path = self._params_dir / "params.json"
        with registry_path.open() as f:
            self._registry: dict[str, str] = json.load(f)

    def _resolve(self, strategy_name: str) -> tuple[type, type[StrategyParams]]:
        full_path = self._registry[strategy_name]
        module_path, class_name = full_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        strategy_cls = getattr(module, class_name)
        params_cls = getattr(module, f"{class_name}Params")
        return strategy_cls, params_cls

    def load(self, strategy_name: str) -> StrategyParams:
        _, params_cls = self._resolve(strategy_name)
        path = self._params_dir / f"{strategy_name}.json"
        with path.open() as f:
            data = json.load(f)
        data["name"] = strategy_name
        return params_cls(**data)

    def load_all(self) -> list[tuple[type, StrategyParams]]:
        result: list[tuple[type, StrategyParams]] = []
        for strategy_name in self._registry:
            strategy_cls, _ = self._resolve(strategy_name)
            result.append((strategy_cls, self.load(strategy_name)))
        return result
