from dataclasses import dataclass


@dataclass
class StrategyParams:
    symbols:  list[str]
    name:     str
    nominal:  float = 1.0
