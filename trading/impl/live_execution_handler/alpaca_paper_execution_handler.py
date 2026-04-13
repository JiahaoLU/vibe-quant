import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from ...base.live.execution import LiveExecutionHandler
from ...events import Event, FillEvent, OrderEvent
from external.alpaca import TERMINAL_ORDER_STATUSES, get_order_status, open_fill_stream, submit_order

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3.0   # seconds between fallback polls


class AlpacaPaperExecutionHandler(LiveExecutionHandler):
    """Routes orders to Alpaca's paper trading API."""

    _PAPER = True

    def __init__(self, emit: Callable[[Event], None], api_key: str, secret: str):
        super().__init__(emit)
        self._api_key = api_key
        self._secret  = secret
        # order_id → (symbol, direction, quantity)
        self._pending_orders: dict[str, tuple[str, str, int]] = {}
        self._filled_order_ids: set[str] = set()

    def execute_order(self, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            self._emit(FillEvent(
                symbol=event.symbol, timestamp=event.timestamp,
                direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
            ))
            return
        order_id = submit_order(
            symbol=event.symbol,
            direction=event.direction,
            quantity=event.quantity,
            api_key=self._api_key,
            secret=self._secret,
            paper=self._PAPER,
        )
        self._pending_orders[order_id] = (event.symbol, event.direction, event.quantity)

    @asynccontextmanager
    async def fill_stream(self):
        """Yields asyncio.Queue[FillEvent]. Bridges WebSocket stream + polling fallback."""
        fill_q: asyncio.Queue = asyncio.Queue()

        async def _bridge_ws(ws_q: asyncio.Queue):
            while True:
                data = await ws_q.get()
                fill = self._translate(data)
                if fill and fill.symbol and fill.symbol in {s for s, _, _ in self._pending_orders.values()}:
                    self._filled_order_ids.add(str(data.order.id))
                    self._pending_orders.pop(str(data.order.id), None)
                    await fill_q.put(fill)

        async def _poll_fallback():
            while True:
                await asyncio.sleep(_POLL_INTERVAL)
                for order_id, (symbol, direction, qty) in list(self._pending_orders.items()):
                    if order_id in self._filled_order_ids:
                        continue
                    status = get_order_status(order_id, self._api_key, self._secret, self._PAPER)
                    if not status:
                        continue
                    order_status = status["status"]
                    if order_status == "filled":
                        fill = FillEvent(
                            symbol=symbol,
                            timestamp=datetime.now(timezone.utc),
                            direction=direction,
                            quantity=status["filled_qty"],
                            fill_price=status["filled_avg_price"],
                            commission=0.0,
                        )
                        self._filled_order_ids.add(order_id)
                        self._pending_orders.pop(order_id, None)
                        await fill_q.put(fill)
                    elif order_status in TERMINAL_ORDER_STATUSES:
                        logger.warning(
                            "Order %s for %s %s×%s cleared with status %s",
                            order_id, symbol, direction, qty, order_status,
                        )
                        self._pending_orders.pop(order_id, None)

        async with open_fill_stream(self._api_key, self._secret, paper=self._PAPER) as ws_q:
            ws_task   = asyncio.create_task(_bridge_ws(ws_q))
            poll_task = asyncio.create_task(_poll_fallback())
            try:
                yield fill_q
            finally:
                ws_task.cancel()
                poll_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ws_task
                with contextlib.suppress(asyncio.CancelledError):
                    await poll_task

    def _translate(self, data) -> FillEvent | None:
        try:
            order     = data.order
            direction = "BUY" if str(order.side) == "buy" else "SELL"
            return FillEvent(
                symbol    = order.symbol,
                timestamp = datetime.now(timezone.utc),
                direction = direction,
                quantity  = int(float(order.filled_qty or 0)),
                fill_price= float(order.filled_avg_price or 0.0),
                commission= 0.0,
            )
        except Exception as exc:
            logger.warning("Failed to translate fill: %s", exc)
            return None
