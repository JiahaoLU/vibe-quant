import asyncio
import queue
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.events import FillEvent, OrderEvent


def _order(symbol="AAPL", direction="BUY", qty=10, price=150.0) -> OrderEvent:
    return OrderEvent(
        symbol=symbol,
        timestamp=datetime(2024, 1, 2),
        order_type="MARKET",
        direction=direction,
        quantity=qty,
        reference_price=price,
    )


def test_paper_execute_order_calls_submit_order():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.alpaca_paper_execution_handler.submit_order", return_value="ord-1") as mock_sub:
        handler.execute_order(_order())

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="key", secret="secret", paper=True,
    )
    assert "ord-1" in handler._pending_orders


def test_live_execute_order_calls_submit_order_with_paper_false():
    from trading.impl.alpaca_execution_handler import AlpacaExecutionHandler

    collected = []
    handler = AlpacaExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    # submit_order is imported in the paper handler module (shared by both handlers)
    with patch("trading.impl.alpaca_paper_execution_handler.submit_order", return_value="ord-2") as mock_sub:
        handler.execute_order(_order(direction="SELL"))

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="SELL", quantity=10,
        api_key="key", secret="secret", paper=False,
    )


def test_execute_order_ignores_hold():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    with patch("trading.impl.alpaca_paper_execution_handler.submit_order") as mock_sub:
        handler.execute_order(_order(direction="HOLD", qty=0))

    mock_sub.assert_not_called()
    assert len(collected) == 1  # HOLD FillEvent emitted immediately
    assert collected[0].direction == "HOLD"


@pytest.mark.asyncio
async def test_fill_stream_yields_fill_events_from_websocket():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from trading.events import EventType
    from contextlib import asynccontextmanager

    raw_fill = MagicMock()
    raw_fill.event = MagicMock()
    raw_fill.event.__str__ = lambda s: "fill"
    raw_fill.order = MagicMock()
    raw_fill.order.id = "ord-1"
    raw_fill.order.symbol = "AAPL"
    raw_fill.order.side = MagicMock()
    raw_fill.order.side.__str__ = lambda s: "buy"
    raw_fill.order.filled_qty = "10"
    raw_fill.order.filled_avg_price = "150.50"

    ws_queue = asyncio.Queue()
    await ws_queue.put(raw_fill)

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    handler = AlpacaPaperExecutionHandler(emit=MagicMock(), api_key="k", secret="s")
    handler._pending_orders["ord-1"] = ("AAPL", "BUY", 10)

    with patch("trading.impl.alpaca_paper_execution_handler.open_fill_stream", _mock_stream):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.type == EventType.FILL
    assert fill_event.symbol == "AAPL"
    assert fill_event.direction == "BUY"
    assert fill_event.quantity == 10
    assert fill_event.fill_price == pytest.approx(150.50)
