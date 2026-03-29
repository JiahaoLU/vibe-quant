import csv
import os
import queue
import tempfile
from datetime import datetime

import pytest

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


def test_missing_symbol_bar_is_zero_filled():
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
        assert bundle.bars["MSFT"].close == 0.0
        assert bundle.bars["MSFT"].open == 0.0
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
