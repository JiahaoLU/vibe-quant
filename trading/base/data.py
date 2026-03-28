from abc import ABC, abstractmethod


class DataHandler(ABC):
    @abstractmethod
    def update_bars(self) -> bool:
        """Emit the next bar bundle as a BarBundleEvent. Returns False when data is exhausted."""
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[dict]:
        """Return the last N bars for a symbol."""
        ...
