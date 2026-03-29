import queue
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from external.yahoo import fetch_daily_bars


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
# fetch_daily_bars tests
# ---------------------------------------------------------------------------

def test_fetch_daily_bars_returns_list_of_dicts():
    df = _make_history_df(AAPL_ROWS)
    with patch("external.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = df
        result = fetch_daily_bars("AAPL", "2020-01-01", "2020-01-04")

    assert len(result) == 2
    assert result[0]["timestamp"] == datetime(2020, 1, 2)
    assert result[0]["open"]      == 100.0
    assert result[0]["high"]      == 101.0
    assert result[0]["low"]       == 99.0
    assert result[0]["close"]     == 100.5
    assert result[0]["volume"]    == 1_000.0


def test_fetch_daily_bars_raises_on_empty_response():
    empty_df = pd.DataFrame()
    with patch("external.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = empty_df
        with pytest.raises(ValueError, match="AAPL"):
            fetch_daily_bars("AAPL", "2020-01-01", "2020-01-04")


from trading.impl.yahoo_data_handler import YahooDataHandler
from trading.events import BarBundleEvent, EventType


# ---------------------------------------------------------------------------
# YahooDataHandler helpers
# ---------------------------------------------------------------------------

def _make_fetch(data: dict[str, list[dict]]):
    """Return a fetch callable that serves pre-canned rows, or raises on unknown symbol."""
    def fetch(symbol: str, start: str, end: str) -> list[dict]:
        if symbol not in data or not data[symbol]:
            raise ValueError(f"No data for {symbol}")
        return data[symbol]
    return fetch


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


def test_handler_missing_bar_is_zero_filled():
    # On Jan 3 MSFT has no bar — should be zero-filled
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2 — both present
    handler.update_bars()  # Jan 3 — MSFT missing
    bundle = collected[1]
    assert bundle.bars["AAPL"].close == 101.0
    assert bundle.bars["MSFT"].close == 0.0


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
