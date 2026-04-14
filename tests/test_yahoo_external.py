import pytest
from datetime import datetime

from external.yahoo import fetch_bars


@pytest.mark.integration
def test_fetch_bars_real_network():
    """Fetch a short date range for a known ticker. Requires internet access."""
    result = fetch_bars(["AAPL"], "2023-01-01", "2023-01-15")
    assert "AAPL" in result
    rows = result["AAPL"]
    assert len(rows) > 0
    row = rows[0]
    assert isinstance(row["timestamp"], datetime)
    assert row["open"]   > 0
    assert row["high"]   >= row["low"]
    assert row["close"]  > 0
    assert row["volume"] > 0


@pytest.mark.integration
def test_fetch_bars_multi_symbol():
    """Fetch two symbols in a single call. Requires internet access."""
    result = fetch_bars(["AAPL", "MSFT"], "2023-01-01", "2023-01-15")
    assert "AAPL" in result
    assert "MSFT" in result
    assert len(result["AAPL"]) > 0
    assert len(result["MSFT"]) > 0


@pytest.mark.integration
def test_fetch_bars_invalid_ticker_raises():
    """An invalid ticker should raise ValueError."""
    with pytest.raises(ValueError):
        fetch_bars(["INVALID_TICKER_XYZ"], "2023-01-01", "2023-01-15")
