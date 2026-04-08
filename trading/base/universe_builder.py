from abc import ABC, abstractmethod
from datetime import datetime


class UniverseBuilder(ABC):
    @abstractmethod
    def is_active(self, symbol: str, timestamp: datetime) -> bool:
        """True if symbol was in the universe at timestamp."""
        ...
