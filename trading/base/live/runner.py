from abc import ABC, abstractmethod


class LiveRunner(ABC):
    @abstractmethod
    async def run(self) -> None:
        """Start the live trading loop. Runs until shutdown."""
        ...
