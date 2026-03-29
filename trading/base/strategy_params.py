from dataclasses import dataclass
from typing import Literal


@dataclass
class StrategyParams:
    symbols:  list[str]

