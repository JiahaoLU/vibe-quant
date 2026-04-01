from typing import Callable

from ..base.execution import ExecutionHandler
from ..events import Event, FillEvent, OrderEvent


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Fills BUY/SELL at reference_price with slippage and percentage commission;
    HOLD passes through as a zero-cost fill.

    commission_pct : fraction of trade value charged per fill, e.g. 0.001 = 0.1%
    slippage_pct   : one-way price impact as a fraction, e.g. 0.0005 = 0.05%
    """

    def __init__(
        self,
        emit:           Callable[[Event], None],
        commission_pct: float = 0.001,
        slippage_pct:   float = 0.0005,
    ):
        super().__init__(emit)
        self._commission_pct = commission_pct
        self._slippage_pct   = slippage_pct

    def execute_order(self, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            self._emit(FillEvent(
                symbol     = event.symbol,
                timestamp  = event.timestamp,
                direction  = "HOLD",
                quantity   = 0,
                fill_price = 0.0,
                commission = 0.0,
            ))
            return

        direction_factor = 1 if event.direction == "BUY" else -1
        fill_price = event.reference_price * (1 + direction_factor * self._slippage_pct)
        commission = fill_price * event.quantity * self._commission_pct

        self._emit(FillEvent(
            symbol     = event.symbol,
            timestamp  = event.timestamp,
            direction  = event.direction,
            quantity   = event.quantity,
            fill_price = fill_price,
            commission = commission,
        ))
