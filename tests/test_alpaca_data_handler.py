import asyncio
from collections import deque
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _raw_bar(symbol="AAPL", o=100.0, h=101.0, l=99.0, c=100.5, v=50000.0):
    return {
        "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def test_get_latest_bars_returns_empty_before_any_bars():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    assert handler.get_latest_bars("AAPL", 1) == []


def test_get_latest_bars_returns_tick_events_after_update():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    fake_bars = {"AAPL": _raw_bar()}
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=fake_bars),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        result = asyncio.run(handler.update_bars_async())

    assert result is True
    ticks = handler.get_latest_bars("AAPL", 1)
    assert len(ticks) == 1
    assert ticks[0].close == 100.5
    assert ticks[0].symbol == "AAPL"


def test_update_bars_async_emits_bar_bundle_event():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from trading.events import EventType

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    fake_bars = {"AAPL": _raw_bar()}
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=fake_bars),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert len(collected) == 1
    assert collected[0].type == EventType.BAR_BUNDLE
    assert "AAPL" in collected[0].bars


def test_update_bars_async_returns_false_when_shutdown_requested():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    async def _run():
        handler.request_shutdown()
        return await handler.update_bars_async()

    result = asyncio.run(_run())
    assert result is False
