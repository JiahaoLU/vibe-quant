from dataclasses import dataclass


@dataclass
class StrategyParams:
    symbols:  list[str]
    nominal:  float = 1.0
    name:     str   = ""

