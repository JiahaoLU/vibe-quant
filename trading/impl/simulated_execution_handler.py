import math
from typing import Callable

from ..base.execution import ExecutionHandler
from ..events import Event, FillEvent, OrderEvent

_PARKINSON_DENOM = 2 * (2 * math.log(2)) ** 0.5  # ≈ 2.3548
_SPREAD_FRACTION = 0.3                             # empirical Roll-model constant


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Fills BUY/SELL orders with a two-component cost model:

    1. Spread floor: max(slippage_pct, 0.3 × (high − low) / close)
       Ensures a realistic minimum cost even for tiny orders.

    2. Volume-scaled market impact (Almgren et al.):
       eta × σ × √(order_qty / bar_volume)
       where σ is the Parkinson intraday-volatility estimate.

    Synthetic bars (is_synthetic=True, typically volume=0) skip both
    impact and spread floor, applying only the fixed slippage_pct.

    commission_pct    : fraction of fill value charged per trade, e.g. 0.001 = 0.1%
    slippage_pct      : fixed spread floor (minimum one-way cost), e.g. 0.0005 = 0.05%
    market_impact_eta : square-root impact coefficient; 0.1–0.3 for liquid US equities
    """

    def __init__(
        self,
        emit:               Callable[[Event], None],
        commission_pct:     float = 0.001,
        slippage_pct:       float = 0.0005,
        market_impact_eta:  float = 0.1,
    ):
        super().__init__(emit)
        self._commission_pct    = commission_pct
        self._slippage_pct      = slippage_pct
        self._market_impact_eta = market_impact_eta

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

        if event.bar_is_synthetic:
            # Synthetic bar: no real price discovery → fixed slippage only
            total_slippage = self._slippage_pct
        else:
            spread_floor = (
                _SPREAD_FRACTION * (event.bar_high - event.bar_low) / event.bar_close
                if event.bar_close > 0 else 0.0
            )
            base_slippage = max(self._slippage_pct, spread_floor)

            if event.bar_volume > 0 and self._market_impact_eta > 0:
                intraday_vol = (
                    (event.bar_high - event.bar_low) / event.bar_close / _PARKINSON_DENOM
                    if event.bar_close > 0 else 0.0
                )
                participation = event.quantity / event.bar_volume
                impact_pct = self._market_impact_eta * intraday_vol * participation ** 0.5
            else:
                impact_pct = 0.0

            total_slippage = base_slippage + impact_pct

        fill_price = event.reference_price * (1 + direction_factor * total_slippage)
        commission = fill_price * event.quantity * self._commission_pct

        self._emit(FillEvent(
            symbol     = event.symbol,
            timestamp  = event.timestamp,
            direction  = event.direction,
            quantity   = event.quantity,
            fill_price = fill_price,
            commission = commission,
        ))
