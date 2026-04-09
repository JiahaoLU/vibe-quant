import asyncio
from abc import abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ...base.execution import ExecutionHandler
from ...events import FillEvent


class LiveExecutionHandler(ExecutionHandler):
    @abstractmethod
    @asynccontextmanager
    async def fill_stream(self) -> AsyncIterator[asyncio.Queue]:
        """Async context manager yielding asyncio.Queue[FillEvent].
        Handles WebSocket connection and polling fallback internally."""
        ...
