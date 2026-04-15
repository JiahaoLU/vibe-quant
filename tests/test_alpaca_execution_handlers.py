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
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order", return_value="ord-1") as mock_sub:
        handler.execute_order(_order())

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="key", secret="secret", paper=True,
        client_order_id="",
    )
    assert "ord-1" in handler._pending_orders


def test_live_execute_order_calls_submit_order_with_paper_false():
    from trading.impl.live_execution_handler.alpaca_execution_handler import AlpacaExecutionHandler

    collected = []
    handler = AlpacaExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    # submit_order is imported in the paper handler module (shared by both handlers)
    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order", return_value="ord-2") as mock_sub:
        handler.execute_order(_order(direction="SELL"))

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="SELL", quantity=10,
        api_key="key", secret="secret", paper=False,
        client_order_id="",
    )


def test_execute_order_ignores_hold():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order") as mock_sub:
        handler.execute_order(_order(direction="HOLD", qty=0))

    mock_sub.assert_not_called()
    assert len(collected) == 1  # HOLD FillEvent emitted immediately
    assert collected[0].direction == "HOLD"


@pytest.mark.asyncio
@pytest.mark.parametrize("terminal_status", [
    "canceled", "cancelled", "rejected", "expired", "done_for_day"
])
async def test_poll_fallback_clears_terminal_orders(terminal_status):
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from contextlib import asynccontextmanager

    ws_queue = asyncio.Queue()

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    handler._pending_orders["ord-99"] = ("AAPL", "BUY", 5, "")

    status_payload = {"status": terminal_status, "filled_qty": 0, "filled_avg_price": 0.0}

    with (
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.get_order_status", return_value=status_payload),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler._POLL_INTERVAL", 0.05),
    ):
        async with handler.fill_stream() as fill_q:
            await asyncio.sleep(0.15)  # allow at least one poll cycle

    assert "ord-99" not in handler._pending_orders
    assert fill_q.empty()   # no FillEvent emitted for terminal orders
    assert collected == []


@pytest.mark.asyncio
async def test_fill_stream_yields_fill_events_from_websocket():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
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
    handler._pending_orders["ord-1"] = ("AAPL", "BUY", 10, "")

    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.type == EventType.FILL
    assert fill_event.symbol == "AAPL"
    assert fill_event.direction == "BUY"
    assert fill_event.quantity == 10
    assert fill_event.fill_price == pytest.approx(150.50)


def test_execute_order_cancels_existing_open_order_for_same_symbol():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-old"] = ("AAPL", "BUY", 100, "")

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order"
        ) as mock_cancel,
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-new",
        ) as mock_submit,
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_cancel.assert_called_once_with("ord-old", "k", "s", True)
    mock_submit.assert_called_once()
    assert "ord-old" not in handler._pending_orders
    assert "ord-new" in handler._pending_orders


def test_execute_order_does_not_cancel_order_for_different_symbol():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-msft"] = ("MSFT", "BUY", 50, "")

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order"
        ) as mock_cancel,
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-aapl",
        ),
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_cancel.assert_not_called()
    assert "ord-msft" in handler._pending_orders
    assert "ord-aapl" in handler._pending_orders


def test_execute_order_stale_order_removed_when_cancel_swallows_broker_error():
    # Real production path: cancel_order swallows the broker error internally and
    # returns normally. The stale order must still be removed from _pending_orders
    # and the new order must be submitted.
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-old"] = ("AAPL", "BUY", 100, "")

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order",
            return_value=None,  # broker error was swallowed inside cancel_order
        ),
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-new",
        ) as mock_submit,
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_submit.assert_called_once()
    assert "ord-old" not in handler._pending_orders
    assert "ord-new" in handler._pending_orders


def test_execute_order_passes_client_order_id_to_submit():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2024, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
        order_id="my-uuid-123",
    )
    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    with patch(
        "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
        return_value="broker-ord-1",
    ) as mock_sub:
        handler.execute_order(order)

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="k", secret="s", paper=True,
        client_order_id="my-uuid-123",
    )


@pytest.mark.asyncio
async def test_fill_stream_ws_echoes_client_order_id_in_fill():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from contextlib import asynccontextmanager

    raw_fill = MagicMock()
    raw_fill.event = MagicMock()
    raw_fill.event.__str__ = lambda s: "fill"
    raw_fill.order = MagicMock()
    raw_fill.order.id = "broker-ord-1"
    raw_fill.order.client_order_id = "my-uuid-123"
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
    handler._pending_orders["broker-ord-1"] = ("AAPL", "BUY", 10, "my-uuid-123")

    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.order_id == "my-uuid-123"


@pytest.mark.asyncio
async def test_poll_fallback_echoes_client_order_id_in_fill():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from contextlib import asynccontextmanager

    ws_queue = asyncio.Queue()

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    handler._pending_orders["broker-ord-1"] = ("AAPL", "BUY", 5, "my-uuid-456")

    status_payload = {
        "status": "filled",
        "filled_qty": 5,
        "filled_avg_price": 150.0,
    }

    with (
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.get_order_status", return_value=status_payload),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler._POLL_INTERVAL", 0.05),
    ):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.order_id == "my-uuid-456"
