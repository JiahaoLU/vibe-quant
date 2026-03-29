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
    {"timestamp": "2020-01-02", "open": 100.0, "high": 101.0, "low": 99.0,  "close": 100.5, "volume": 1_000.0},
    {"timestamp": "2020-01-03", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1_100.0},
]
MSFT_ROWS = [
    {"timestamp": "2020-01-02", "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2_000.0},
    {"timestamp": "2020-01-04", "open": 200.5, "high": 202.0, "low": 200.0, "close": 201.0, "volume": 2_100.0},
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
