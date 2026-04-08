from abc import ABC, abstractmethod

from .strategy_params import StrategyParams


class StrategyParamsLoader(ABC):
    @abstractmethod
    def load(self, strategy_name: str) -> StrategyParams:
        """Load and return params for a single registered strategy."""
        ...

    @abstractmethod
    def load_all(self) -> list[tuple[type, StrategyParams]]:
        """Load and return all registered strategies as (StrategyClass, StrategyParams) pairs."""
        ...
