import queue

from .base.data      import DataHandler
from .base.execution import ExecutionHandler
from .base.portfolio import Portfolio
from .base.strategy  import StrategySignalGenerator
from .events         import EventType


class Backtester:
    def __init__(
        self,
        events:    queue.Queue,
        data:      DataHandler,
        strategy:  StrategySignalGenerator,
        portfolio: Portfolio,
        execution: ExecutionHandler,
    ):
        self._events    = events
        self._data      = data
        self._strategy  = strategy
        self._portfolio = portfolio
        self._execution = execution

    def run(self) -> None:
        while True:
            # Drain the event queue fully before advancing to the next bar
            while not self._events.empty():
                event = self._events.get(block=False)
                match event.type:
                    case EventType.BAR_BUNDLE:
                        self._portfolio.fill_pending_orders(event)   # fill T-1 pending at bar T open
                        self._strategy.get_signals(event)            # generate signals from bar T close
                    case EventType.SIGNAL_BUNDLE:
                        self._portfolio.on_signal(event)
                    case EventType.ORDER:
                        self._execution.execute_order(event)
                    case EventType.FILL:
                        self._portfolio.on_fill(event)

            # Advance to the next bar; stop when data is exhausted
            if not self._data.update_bars():
                break

        # Drain any remaining events after the last bar
        while not self._events.empty():
            event = self._events.get(block=False)
            match event.type:
                case EventType.BAR_BUNDLE:
                    self._strategy.get_signals(event)
                case EventType.SIGNAL_BUNDLE:
                    self._portfolio.on_signal(event)
                case EventType.ORDER:
                    self._execution.execute_order(event)
                case EventType.FILL:
                    self._portfolio.on_fill(event)
