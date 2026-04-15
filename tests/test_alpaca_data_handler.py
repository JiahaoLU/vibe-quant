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


def test_prefill_populates_deques_with_historical_bars():
    from trading.events import TickEvent
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=200,
    )

    fake_history = {
        "AAPL": [
            _raw_bar(c=100.5),
            {
                "timestamp": datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc),
                "open": 101.0,
                "high": 102.0,
                "low": 100.0,
                "close": 101.5,
                "volume": 60000.0,
            },
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 2
    assert bars[0].close == pytest.approx(100.5)
    assert bars[1].close == pytest.approx(101.5)
    assert isinstance(bars[0], TickEvent)


def test_prefill_does_not_emit_events():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value={"AAPL": [_raw_bar()]},
    ):
        handler.prefill()

    assert collected == []


def test_prefill_skips_symbol_missing_from_history():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL", "MSFT"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value={"AAPL": [_raw_bar()]},
    ):
        handler.prefill()

    assert len(handler.get_latest_bars("AAPL", 1)) == 1
    assert handler.get_latest_bars("MSFT", 1) == []


def test_prefill_respects_max_history_deque_limit():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=3,
    )

    fake_history = {
        "AAPL": [
            {
                "timestamp": datetime(2024, 1, day, 21, 5, tzinfo=timezone.utc),
                "open": float(100 + day),
                "high": float(101 + day),
                "low": float(99 + day),
                "close": float(100.5 + day),
                "volume": 50000.0,
            }
            for day in range(1, 6)
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 3
    assert bars[-1].close == pytest.approx(105.5)


def test_prefill_daily_requests_max_history_times_two_calendar_days():
    from datetime import timedelta

    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=200,
    )

    calls = []

    def fake_fetch_history(**kwargs):
        calls.append(kwargs)
        return {}

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        side_effect=fake_fetch_history,
    ):
        handler.prefill()

    assert len(calls) == 1
    span = calls[0]["end"] - calls[0]["start"]
    assert span >= timedelta(days=399)   # 200 * 2 days, allow 1-day float


def test_prefill_intraday_requests_bar_minutes_times_max_history_times_three():
    from datetime import timedelta

    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="5m",
        api_key="key",
        secret="secret",
        max_history=200,
    )

    calls = []

    def fake_fetch_history(**kwargs):
        calls.append(kwargs)
        return {}

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        side_effect=fake_fetch_history,
    ):
        handler.prefill()

    assert len(calls) == 1
    span = calls[0]["end"] - calls[0]["start"]
    # 200 bars * 5 min * 3 = 3000 minutes; verify window is in that range (±1 min float)
    assert timedelta(minutes=2999) <= span <= timedelta(minutes=3001)


def test_prefill_warning_fired_with_symbol_name_when_no_history():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL", "MSFT"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    # MSFT has no bars
    fake_history = {"AAPL": [_raw_bar()]}

    with (
        patch(
            "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
            return_value=fake_history,
        ),
        patch("trading.impl.data_handler.alpaca_data_handler.logger") as mock_log,
    ):
        handler.prefill()

    mock_log.warning.assert_called_once()
    assert "MSFT" in mock_log.warning.call_args[0][1]


def test_prefill_propagates_api_exception():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    with (
        patch(
            "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
            side_effect=RuntimeError("API unavailable"),
        ),
        pytest.raises(RuntimeError, match="API unavailable"),
    ):
        handler.prefill()


def test_update_bars_async_sets_is_end_of_day_true_for_daily_bar():
    """Daily bars explicitly pass is_end_of_day=True to BarBundleEvent constructor."""
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from trading.events import BarBundleEvent

    handler = AlpacaDataHandler(
        emit=MagicMock(), symbols=["AAPL"], bar_freq="1d",
        api_key="key", secret="secret",
    )
    raw = {
        "AAPL": {
            "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    construct_calls = []
    real_BarBundleEvent = BarBundleEvent

    def spy_bundle(*args, **kwargs):
        construct_calls.append((args, kwargs))
        return real_BarBundleEvent(*args, **kwargs)

    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
        patch("trading.impl.data_handler.alpaca_data_handler.BarBundleEvent", side_effect=spy_bundle),
    ):
        asyncio.run(handler.update_bars_async())

    assert len(construct_calls) == 1
    args, kwargs = construct_calls[0]
    # is_end_of_day may be passed as kwarg or (if dataclass field order: timestamp, bars, is_end_of_day) as args[2]
    assert kwargs.get("is_end_of_day") is True or (len(args) > 2 and args[2] is True)


def test_update_bars_async_sets_is_end_of_day_true_for_last_intraday_bar():
    """Intraday bar whose slot ends at market close has is_end_of_day=True.

    For 5m bars, the last bar starts at 15:55 ET (15:55 + 5m = 16:00 = close).
    Alpaca returns timestamps in UTC; 15:55 ET = 20:55 UTC in winter.
    """
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from zoneinfo import ZoneInfo

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append, symbols=["AAPL"], bar_freq="5m",
        api_key="key", secret="secret",
    )
    # 15:55 ET on a non-DST day = 20:55 UTC
    last_bar_ts = datetime(2024, 1, 2, 20, 55, tzinfo=ZoneInfo("UTC"))
    raw = {
        "AAPL": {
            "timestamp": last_bar_ts,
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert collected[0].is_end_of_day is True


def test_update_bars_async_sets_is_end_of_day_false_for_mid_session_intraday_bar():
    """Intraday bar in the middle of the session has is_end_of_day=False."""
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from zoneinfo import ZoneInfo

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append, symbols=["AAPL"], bar_freq="5m",
        api_key="key", secret="secret",
    )
    # 10:00 ET = 15:00 UTC (mid-session)
    mid_bar_ts = datetime(2024, 1, 2, 15, 0, tzinfo=ZoneInfo("UTC"))
    raw = {
        "AAPL": {
            "timestamp": mid_bar_ts,
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert collected[0].is_end_of_day is False
