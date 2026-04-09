import csv
import os
import queue
import tempfile
from datetime import datetime
from unittest.mock import MagicMock

import pytest

from trading.base.universe_builder import UniverseBuilder
from trading.impl.multi_csv_data_handler import MultiCSVDataHandler
from trading.events import BarBundleEvent, EventType


def make_csv(rows: list[dict]) -> str:
    """Write OHLCV rows to a temp CSV and return the file path."""
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    writer = csv.DictWriter(
        f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"]
    )
    writer.writeheader()
    writer.writerows(rows)
    f.close()
    return f.name


def _make_universe_builder_csv(active_until: dict[str, datetime]):
    builder = MagicMock(spec=UniverseBuilder)

    def is_active(symbol, timestamp):
        if symbol not in active_until:
            return True
        return timestamp < active_until[symbol]

    builder.is_active.side_effect = is_active
    return builder


AAPL_ROWS = [
    {"timestamp": "2020-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
    {"timestamp": "2020-01-03", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1100},
]
# MSFT has 2020-01-02 and 2020-01-04 — no overlap with AAPL's 2020-01-03
MSFT_ROWS = [
    {"timestamp": "2020-01-02", "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2000},
    {"timestamp": "2020-01-04", "open": 200.5, "high": 202.0, "low": 200.0, "close": 201.0, "volume": 2100},
]


def test_update_bars_emits_bar_bundle_event():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        assert handler.update_bars() is True
        event = events.get_nowait()
        assert isinstance(event, BarBundleEvent)
        assert event.type == EventType.BAR_BUNDLE
        assert "AAPL" in event.bars
        assert "MSFT" in event.bars
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_timestamps_are_union_sorted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        # Union: 2020-01-02, 2020-01-03, 2020-01-04 — 3 timesteps
        count = 0
        while handler.update_bars():
            count += 1
        assert count == 3
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_missing_symbol_bar_is_carry_forwarded():
    """Missing bar uses last known real price, not zero."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — both present
        events.get_nowait()
        handler.update_bars()  # 2020-01-03 — MSFT missing
        bundle = events.get_nowait()
        assert bundle.bars["AAPL"].close == 101.0
        assert bundle.bars["AAPL"].is_synthetic is False
        assert bundle.bars["MSFT"].close == 200.5   # carry-forward from 2020-01-02
        assert bundle.bars["MSFT"].is_synthetic is True
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_synthetic_bar_excluded_from_history():
    """Synthetic (carry-forward) bars are not stored in the deque."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — MSFT real
        handler.update_bars()  # 2020-01-03 — MSFT synthetic (skipped from deque)
        bars = handler.get_latest_bars("MSFT", 5)
        assert len(bars) == 1                        # only the Jan 2 real bar
        assert bars[0].close == 200.5
        assert bars[0].is_synthetic is False
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_real_bar_after_gap_resumes_history():
    """A real bar after a synthetic gap resumes history normally."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — MSFT real
        handler.update_bars()  # 2020-01-03 — MSFT synthetic
        handler.update_bars()  # 2020-01-04 — MSFT real again
        bars = handler.get_latest_bars("MSFT", 5)
        assert len(bars) == 2                        # Jan 2 and Jan 4 — no synthetic
        assert bars[0].close == 200.5                # Jan 2
        assert bars[1].close == 201.0                # Jan 4
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_present_bars_have_correct_values():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02
        bundle = events.get_nowait()
        assert bundle.bars["AAPL"].close == 100.5
        assert bundle.bars["MSFT"].close == 200.5
        assert bundle.timestamp == datetime(2020, 1, 2)
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_get_latest_bars_returns_history():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02
        handler.update_bars()  # 2020-01-03
        bars = handler.get_latest_bars("AAPL", 2)
        assert len(bars) == 2
        assert bars[-1].close == 101.0
        assert bars[0].close == 100.5
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_get_latest_bars_partial_history():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # only 1 bar so far
        bars = handler.get_latest_bars("AAPL", 10)
        assert len(bars) == 1  # fewer than requested
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_update_bars_returns_false_when_exhausted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        handler.update_bars()
        handler.update_bars()
        assert handler.update_bars() is False
    finally:
        os.unlink(aapl)
        os.unlink(msft)


# ---------------------------------------------------------------------------
# Random generation mode
# ---------------------------------------------------------------------------

def test_random_mode_emits_bar_bundle_events():
    events = queue.Queue()
    handler = MultiCSVDataHandler(events.put, ["AAPL"], start="2020-01-01", end="2020-02-01")
    assert handler.update_bars() is True
    event = events.get_nowait()
    assert isinstance(event, BarBundleEvent)
    assert "AAPL" in event.bars


def test_random_mode_only_weekday_bars():
    events = queue.Queue()
    handler = MultiCSVDataHandler(events.put, ["AAPL"], start="2020-01-01", end="2020-01-15")
    timestamps = []
    while handler.update_bars():
        timestamps.append(events.get_nowait().timestamp)
    assert all(ts.weekday() < 5 for ts in timestamps)


def test_random_mode_bar_values_are_valid():
    events = queue.Queue()
    handler = MultiCSVDataHandler(events.put, ["AAPL"], start="2020-01-01", end="2020-01-15")
    handler.update_bars()
    bar = events.get_nowait().bars["AAPL"]
    assert bar.open   > 0
    assert bar.high   >= bar.low
    assert bar.close  > 0
    assert bar.volume > 0


def test_random_mode_is_reproducible():
    q1, q2 = queue.Queue(), queue.Queue()
    h1 = MultiCSVDataHandler(q1.put, ["AAPL"], start="2020-01-01", end="2020-02-01")
    h2 = MultiCSVDataHandler(q2.put, ["AAPL"], start="2020-01-01", end="2020-02-01")
    bars1, bars2 = [], []
    while h1.update_bars():
        bars1.append(q1.get_nowait().bars["AAPL"].close)
    while h2.update_bars():
        bars2.append(q2.get_nowait().bars["AAPL"].close)
    assert bars1 == bars2


def test_random_mode_raises_without_start_end():
    with pytest.raises(ValueError):
        MultiCSVDataHandler(queue.Queue().put, ["AAPL"])


def test_csv_handler_marks_exit_bar_as_delisted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        ub = _make_universe_builder_csv({"AAPL": datetime(2020, 1, 3)})
        collected = []
        handler = MultiCSVDataHandler(
            collected.append,
            ["AAPL", "MSFT"],
            [aapl, msft],
            universe_builder=ub,
        )
        handler.update_bars()
        assert collected[0].bars["AAPL"].is_delisted is False
        handler.update_bars()
        assert collected[1].bars["AAPL"].is_delisted is True
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_csv_handler_excludes_symbol_after_exit_bar():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        ub = _make_universe_builder_csv({"AAPL": datetime(2020, 1, 3)})
        collected = []
        handler = MultiCSVDataHandler(
            collected.append,
            ["AAPL", "MSFT"],
            [aapl, msft],
            universe_builder=ub,
        )
        while handler.update_bars():
            pass
        assert "AAPL" not in collected[-1].bars
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_csv_handler_without_universe_builder_unchanged():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        collected = []
        handler = MultiCSVDataHandler(collected.append, ["AAPL", "MSFT"], [aapl, msft])
        while handler.update_bars():
            pass
        assert all(not bar.is_delisted for bundle in collected for bar in bundle.bars.values())
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_update_bars_async_default_calls_update_bars():
    """Default update_bars_async() wraps update_bars() in a thread."""
    import asyncio
    from unittest.mock import patch

    handler = MultiCSVDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-10",
    )
    with patch.object(handler, "update_bars", return_value=False) as mock_sync:
        result = asyncio.run(handler.update_bars_async())
    assert result is False
    mock_sync.assert_called_once()
