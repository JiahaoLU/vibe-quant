import asyncio
import logging
import queue
import signal

from .base.live.execution  import LiveExecutionHandler
from .base.live.reconciler import PositionReconciler
from .base.live.risk_guard import RiskGuard
from .base.live.runner     import LiveRunner as LiveRunnerBase
from .base.portfolio       import Portfolio
from .base.strategy        import StrategySignalGenerator
from .base.data            import DataHandler
from .events               import EventType

logger = logging.getLogger(__name__)


class LiveRunner(LiveRunnerBase):
    """
    Asyncio event loop for live/paper trading.

    Lifecycle:
      1. reconciler.hydrate(portfolio) — load broker positions
      2. Open fill stream (WebSocket + polling fallback)
      3. Drain fill stream as background task
      4. Loop: await next bar → drain event queue → dispatch
      5. Shutdown on SIGTERM / KeyboardInterrupt

    Event dispatch is identical to Backtester.run().
    """

    def __init__(
        self,
        events:     queue.Queue,
        data:       DataHandler,
        strategy:   StrategySignalGenerator,
        portfolio:  Portfolio,
        execution:  LiveExecutionHandler,
        reconciler: PositionReconciler,
        risk_guard: RiskGuard | None = None,
    ):
        self._events     = events
        self._data       = data
        self._strategy   = strategy
        self._portfolio  = portfolio
        self._execution  = execution
        self._reconciler = reconciler
        self._risk_guard = risk_guard
        self._shutdown   = False

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except (OSError, NotImplementedError):
                pass  # signal handlers may not be supported in all environments

        await self._reconciler.hydrate(self._portfolio)
        self._data.prefill()
        if self._risk_guard is not None:
            self._risk_guard.reset_day(self._portfolio.equity)

        async with self._execution.fill_stream() as fill_q:
            drain_task = asyncio.create_task(self._drain_fill_stream(fill_q))
            try:
                while not self._shutdown:
                    bar_ready = await self._data.update_bars_async()
                    if not bar_ready:
                        break
                    while not self._events.empty():
                        try:
                            event = self._events.get_nowait()
                        except queue.Empty:
                            break
                        self._dispatch(event)
            finally:
                drain_task.cancel()
                try:
                    await drain_task
                except asyncio.CancelledError:
                    pass

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested.")
        self._shutdown = True
        if hasattr(self._data, "request_shutdown"):
            self._data.request_shutdown()

    async def _drain_fill_stream(self, fill_q: asyncio.Queue) -> None:
        while True:
            try:
                fill_event = await asyncio.wait_for(fill_q.get(), timeout=0.5)
                self._events.put(fill_event)
            except asyncio.TimeoutError:
                continue

    def _dispatch(self, event) -> None:
        match event.type:
            case EventType.BAR_BUNDLE:
                self._portfolio.fill_pending_orders(event)
                self._strategy.get_signals(event)
            case EventType.STRATEGY_BUNDLE:
                self._portfolio.on_signal(event)
            case EventType.ORDER:
                self._execution.execute_order(event)
            case EventType.FILL:
                self._portfolio.on_fill(event)
