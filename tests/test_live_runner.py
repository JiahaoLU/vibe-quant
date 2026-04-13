import asyncio
import queue
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.events import (
    BarBundleEvent, EventType, FillEvent, OrderEvent,
    SignalEvent, StrategyBundleEvent, TickEvent,
)


def _bar_bundle():
    ts = datetime(2024, 1, 2, 16, 5)
    tick = TickEvent(symbol="AAPL", timestamp=ts,
                     open=150.0, high=151.0, low=149.0, close=150.0, volume=1000.0)
    return BarBundleEvent(timestamp=ts, bars={"AAPL": tick})


@asynccontextmanager
async def _null_fill_stream():
    yield asyncio.Queue()   # empty queue — no fills arrive


@pytest.mark.asyncio
async def test_runner_calls_reconciler_hydrate_before_first_bar():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)  # stop immediately
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    reconciler.hydrate.assert_called_once_with(portfolio)


@pytest.mark.asyncio
async def test_runner_calls_prefill_on_data_handler():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    data.prefill = MagicMock()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    data.prefill.assert_called_once_with()


@pytest.mark.asyncio
async def test_runner_prefill_called_after_hydrate_before_first_bar():
    from trading.live_runner import LiveRunner

    call_order = []
    events = queue.Queue()
    data = MagicMock()

    async def _update():
        call_order.append("bar")
        return False

    data.update_bars_async = _update
    data.prefill = MagicMock(side_effect=lambda: call_order.append("prefill"))
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()

    async def _hydrate(_portfolio):
        call_order.append("hydrate")

    reconciler.hydrate = _hydrate

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    assert call_order.index("hydrate") < call_order.index("prefill")
    assert call_order.index("prefill") < call_order.index("bar")
@pytest.mark.asyncio
async def test_runner_dispatches_bar_bundle_to_portfolio_and_strategy():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    bundle = _bar_bundle()
    events.put(bundle)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1   # True first call, False second
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    portfolio.fill_pending_orders.assert_called_once_with(bundle)
    strategy.get_signals.assert_called_once_with(bundle)


@pytest.mark.asyncio
async def test_runner_dispatches_order_to_execution():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    ts = datetime(2024, 1, 2, 16, 5)
    order = OrderEvent(symbol="AAPL", timestamp=ts, order_type="MARKET",
                       direction="BUY", quantity=5)
    events.put(order)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    execution.execute_order.assert_called_once_with(order)


@pytest.mark.asyncio
async def test_runner_puts_fill_events_from_stream_onto_queue():
    from trading.live_runner import LiveRunner

    fill_event = FillEvent(
        symbol="AAPL", timestamp=datetime(2024, 1, 2, 16, 5),
        direction="BUY", quantity=5, fill_price=150.0, commission=0.0,
    )

    @asynccontextmanager
    async def _fill_stream_with_one_fill():
        q = asyncio.Queue()
        await q.put(fill_event)
        yield q

    events = queue.Queue()
    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)   # give drain task time to forward the fill
        return call_count == 1
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _fill_stream_with_one_fill
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    portfolio.on_fill.assert_called_once_with(fill_event)


@pytest.mark.asyncio
async def test_runner_calls_risk_guard_reset_day_after_prefill():
    """reset_day() must be called with portfolio.equity after hydrate+prefill."""
    from trading.live_runner import LiveRunner
    from unittest.mock import MagicMock

    call_order = []

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    data.prefill = MagicMock(side_effect=lambda: call_order.append("prefill"))

    portfolio = MagicMock()
    portfolio.equity = 9_800.0

    risk_guard = MagicMock()
    risk_guard.reset_day = MagicMock(side_effect=lambda eq: call_order.append(("reset_day", eq)))

    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock(side_effect=lambda _p: call_order.append("hydrate"))

    runner = LiveRunner(events, data, MagicMock(), portfolio, execution, reconciler, risk_guard)
    await runner.run()

    risk_guard.reset_day.assert_called_once_with(9_800.0)
    assert call_order.index("prefill") < call_order.index(("reset_day", 9_800.0))


@pytest.mark.asyncio
async def test_runner_skips_reset_day_when_no_risk_guard():
    """LiveRunner must not error when risk_guard is omitted."""
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    # No risk_guard argument — must complete without AttributeError
    runner = LiveRunner(events, data, MagicMock(), portfolio, execution, reconciler)
    await runner.run()  # should not raise
