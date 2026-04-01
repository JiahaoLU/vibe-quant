import queue

from .base.data          import DataHandler
from .base.execution     import ExecutionHandler
from .base.portfolio     import Portfolio
from .base.result_writer import BacktestResultWriter
from .base.strategy      import StrategySignalGenerator
from .events             import EventType


class Backtester:
    def __init__(
        self,
        events:         queue.Queue,
        data:           DataHandler,
        strategy:       StrategySignalGenerator,
        portfolio:      Portfolio,
        execution:      ExecutionHandler,
        result_writer:  BacktestResultWriter | None = None,
    ):
        self._events        = events
        self._data          = data
        self._strategy      = strategy
        self._portfolio     = portfolio
        self._execution     = execution
        self._result_writer = result_writer

    def run(self) -> None:
        while True:
            while not self._events.empty():
                event = self._events.get(block=False)
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

            if not self._data.update_bars():
                break

        while not self._events.empty():
            event = self._events.get(block=False)
            match event.type:
                case EventType.BAR_BUNDLE:
                    self._strategy.get_signals(event)
                case EventType.STRATEGY_BUNDLE:
                    self._portfolio.on_signal(event)
                case EventType.ORDER:
                    self._execution.execute_order(event)
                case EventType.FILL:
                    self._portfolio.on_fill(event)

        if self._result_writer is not None:
            self._result_writer.write(self._portfolio)
