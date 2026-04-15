import queue
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from external.yahoo import fetch_bars
from trading.base.universe_builder import UniverseBuilder
from trading.impl.data_handler.yahoo_data_handler import YahooDataHandler
from trading.events import BarBundleEvent, EventType


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame that mirrors what yfinance Ticker.history() returns."""
    index = pd.DatetimeIndex(
        [pd.Timestamp(r["timestamp"], tz="UTC") for r in rows]
    )
    return pd.DataFrame(
        {
            "Open":   [r["open"]   for r in rows],
            "High":   [r["high"]   for r in rows],
            "Low":    [r["low"]    for r in rows],
            "Close":  [r["close"]  for r in rows],
            "Volume": [r["volume"] for r in rows],
        },
        index=index,
    )


AAPL_ROWS = [
    {"timestamp": datetime(2020, 1, 2), "open": 100.0, "high": 101.0, "low": 99.0,  "close": 100.5, "volume": 1_000.0},
    {"timestamp": datetime(2020, 1, 3), "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1_100.0},
]
MSFT_ROWS = [
    {"timestamp": datetime(2020, 1, 2), "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2_000.0},
    {"timestamp": datetime(2020, 1, 4), "open": 200.5, "high": 202.0, "low": 200.0, "close": 201.0, "volume": 2_100.0},
]


# ---------------------------------------------------------------------------
# fetch_bars tests
# ---------------------------------------------------------------------------

def test_fetch_bars_returns_dict_of_lists():
    df = _make_history_df(AAPL_ROWS)
    with patch("external.yahoo.yf.download") as mock_download:
        mock_download.return_value = df
        result = fetch_bars(["AAPL"], "2020-01-01", "2020-01-04")

    assert "AAPL" in result
    rows = result["AAPL"]
    assert len(rows) == 2
    assert rows[0]["timestamp"] == datetime(2020, 1, 2)
    assert rows[0]["open"]      == 100.0
    assert rows[0]["high"]      == 101.0
    assert rows[0]["low"]       == 99.0
    assert rows[0]["close"]     == 100.5
    assert rows[0]["volume"]    == 1_000.0


def test_fetch_bars_raises_on_empty_response():
    empty_df = pd.DataFrame()
    with patch("external.yahoo.yf.download") as mock_download:
        mock_download.return_value = empty_df
        with pytest.raises(ValueError):
            fetch_bars(["AAPL"], "2020-01-01", "2020-01-04")


# ---------------------------------------------------------------------------
# YahooDataHandler helpers
# ---------------------------------------------------------------------------

def _make_fetch(data: dict[str, list[dict]]):
    """Return a fetch callable that serves pre-canned rows, or raises on unknown symbol."""
    def fetch(symbols: list[str], start: str, end: str, bar_freq: str = "1d") -> dict[str, list[dict]]:
        result = {}
        for symbol in symbols:
            if symbol not in data or not data[symbol]:
                raise ValueError(f"No data for {symbol}")
            result[symbol] = data[symbol]
        return result
    return fetch


def _make_universe_builder(active_until: dict[str, datetime]):
    builder = MagicMock(spec=UniverseBuilder)

    def is_active(symbol, timestamp):
        if symbol not in active_until:
            return True
        return timestamp < active_until[symbol]

    builder.is_active.side_effect = is_active
    return builder


# ---------------------------------------------------------------------------
# YahooDataHandler tests
# ---------------------------------------------------------------------------

def test_handler_update_bars_emits_bar_bundle_event():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    assert handler.update_bars() is True
    assert len(collected) == 1
    assert isinstance(collected[0], BarBundleEvent)
    assert collected[0].type == EventType.BAR_BUNDLE
    assert "AAPL" in collected[0].bars
    assert "MSFT" in collected[0].bars


def test_handler_timeline_is_union_of_symbol_timestamps():
    # AAPL: Jan 2, Jan 3 — MSFT: Jan 2, Jan 4 → union: Jan 2, Jan 3, Jan 4
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    count = 0
    while handler.update_bars():
        count += 1
    assert count == 3


def test_handler_missing_bar_is_carry_forwarded():
    """Missing bar uses last known real price, not zero."""
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2 — both present
    handler.update_bars()  # Jan 3 — MSFT missing
    bundle = collected[1]
    assert bundle.bars["AAPL"].close == 101.0
    assert bundle.bars["AAPL"].is_synthetic is False
    assert bundle.bars["MSFT"].close == 200.5   # carry-forward from Jan 2
    assert bundle.bars["MSFT"].is_synthetic is True


def test_handler_synthetic_bar_excluded_from_history():
    """Synthetic (carry-forward) bars are not stored in the deque."""
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2 — MSFT real
    handler.update_bars()  # Jan 3 — MSFT synthetic (skipped from deque)
    bars = handler.get_latest_bars("MSFT", 5)
    assert len(bars) == 1                        # only the Jan 2 real bar
    assert bars[0].close == 200.5
    assert bars[0].is_synthetic is False


def test_handler_get_latest_bars_returns_history():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2
    handler.update_bars()  # Jan 3
    bars = handler.get_latest_bars("AAPL", 2)
    assert len(bars) == 2
    assert bars[-1].close == 101.0
    assert bars[0].close  == 100.5


def test_handler_get_latest_bars_partial_history():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # only 1 bar so far
    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 1


def test_handler_update_bars_returns_false_when_exhausted():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    while handler.update_bars():
        pass
    assert handler.update_bars() is False


def test_handler_raises_on_unknown_symbol():
    fetch = _make_fetch({})  # returns nothing for any symbol
    with pytest.raises(ValueError):
        YahooDataHandler([].append, ["INVALID"], "2020-01-01", "2020-01-05", fetch=fetch)


def test_handler_marks_exit_bar_as_delisted():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    ub = _make_universe_builder({"AAPL": datetime(2020, 1, 3)})
    collected = []
    handler = YahooDataHandler(
        collected.append,
        ["AAPL", "MSFT"],
        "2020-01-01",
        "2020-01-05",
        fetch=fetch,
        universe_builder=ub,
    )

    handler.update_bars()
    assert collected[0].bars["AAPL"].is_delisted is False

    handler.update_bars()
    assert collected[1].bars["AAPL"].is_delisted is True


def test_handler_excludes_symbol_after_exit_bar():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    ub = _make_universe_builder({"AAPL": datetime(2020, 1, 3)})
    collected = []
    handler = YahooDataHandler(
        collected.append,
        ["AAPL", "MSFT"],
        "2020-01-01",
        "2020-01-05",
        fetch=fetch,
        universe_builder=ub,
    )
    while handler.update_bars():
        pass
    assert "AAPL" not in collected[-1].bars


def test_handler_without_universe_builder_unchanged():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    while handler.update_bars():
        pass
    assert all(not bar.is_delisted for bundle in collected for bar in bundle.bars.values())


def test_update_bars_daily_bars_always_end_of_day():
    """Every daily bar emitted by YahooDataHandler has is_end_of_day=True."""
    rows = {
        "AAPL": [
            {"timestamp": datetime(2020, 1, 2), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
            {"timestamp": datetime(2020, 1, 3), "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1100.0},
        ]
    }
    collected = []
    handler = YahooDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-04",
        fetch=lambda syms, start, end, freq: rows,
        bar_freq="1d",
    )
    while handler.update_bars():
        pass

    assert all(e.is_end_of_day for e in collected)


def test_update_bars_intraday_only_last_bar_of_day_is_eod():
    """For intraday data, only the last bar in each calendar day has is_end_of_day=True."""
    rows = {
        "AAPL": [
            # Day 1: three 5m bars
            {"timestamp": datetime(2020, 1, 2, 9, 30), "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.2, "volume": 100.0},
            {"timestamp": datetime(2020, 1, 2, 9, 35), "open": 100.2, "high": 100.8, "low": 100.0, "close": 100.5, "volume": 110.0},
            {"timestamp": datetime(2020, 1, 2, 9, 40), "open": 100.5, "high": 101.0, "low": 100.3, "close": 100.9, "volume": 120.0},
            # Day 2: two 5m bars
            {"timestamp": datetime(2020, 1, 3, 9, 30), "open": 101.0, "high": 101.5, "low": 100.8, "close": 101.2, "volume": 130.0},
            {"timestamp": datetime(2020, 1, 3, 9, 35), "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.5, "volume": 140.0},
        ]
    }
    collected = []
    handler = YahooDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-04",
        fetch=lambda syms, start, end, freq: rows,
        bar_freq="5m",
    )
    while handler.update_bars():
        pass

    eod_flags = [e.is_end_of_day for e in collected]
    # 5 bars total: [False, False, True, False, True]
    assert eod_flags == [False, False, True, False, True]
