from typing import Callable

from ..base.execution import ExecutionHandler
from ..events import Event, FillEvent, OrderEvent


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Fills at reference_price (current bar close) with slippage and flat commission.
    BUYs fill slightly higher, SELLs slightly lower.
    """

    def __init__(
        self,
        emit:         Callable[[Event], None],
        commission:   float = 1.0,
        slippage_pct: float = 0.0005,
    ):
        super().__init__(emit)
        self._commission   = commission
        self._slippage_pct = slippage_pct

    def execute_order(self, event: OrderEvent) -> None:
        direction_factor = 1 if event.direction == "BUY" else -1
        fill_price = event.reference_price * (1 + direction_factor * self._slippage_pct)

        self._emit(FillEvent(
            symbol     = event.symbol,
            timestamp  = event.timestamp,
            direction  = event.direction,
            quantity   = event.quantity,
            fill_price = fill_price,
            commission = self._commission,
        ))
