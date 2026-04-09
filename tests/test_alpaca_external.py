"""Tests for external/alpaca.py — all alpaca-py SDK calls are mocked."""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def _mock_bar(symbol, o=100.0, h=101.0, l=99.0, c=100.5, v=50000):
    bar = MagicMock()
    bar.open = o
    bar.high = h
    bar.low = l
    bar.close = c
    bar.volume = v
    bar.timestamp = datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)
    return bar


def test_fetch_bars_returns_dict_of_dicts():
    from external.alpaca import fetch_bars

    mock_client = MagicMock()
    mock_bar_set = MagicMock()
    mock_bar_set.__getitem__ = lambda self, sym: [_mock_bar(sym)]
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 2),
            end=datetime(2024, 1, 3),
            api_key="key",
            secret="secret",
        )

    assert "AAPL" in result
    assert result["AAPL"]["close"] == 100.5
    assert result["AAPL"]["open"] == 100.0


def test_submit_order_returns_order_id():
    from external.alpaca import submit_order

    mock_client = MagicMock()
    mock_order = MagicMock()
    mock_order.id = "order-123"
    mock_client.submit_order.return_value = mock_order

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        order_id = submit_order(
            symbol="AAPL",
            direction="BUY",
            quantity=10,
            api_key="key",
            secret="secret",
            paper=True,
        )

    assert order_id == "order-123"


def test_get_positions_returns_symbol_qty_dict():
    from external.alpaca import get_positions

    mock_client = MagicMock()
    pos = MagicMock()
    pos.symbol = "AAPL"
    pos.qty = "5"
    mock_client.get_all_positions.return_value = [pos]

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        result = get_positions(api_key="key", secret="secret", paper=True)

    assert result == {"AAPL": 5}


def test_get_account_returns_cash_float():
    from external.alpaca import get_account

    mock_client = MagicMock()
    acct = MagicMock()
    acct.cash = "9500.50"
    mock_client.get_account.return_value = acct

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        result = get_account(api_key="key", secret="secret", paper=True)

    assert result == pytest.approx(9500.50)


def test_get_order_status_returns_fill_info():
    from external.alpaca import get_order_status

    mock_client = MagicMock()
    order = MagicMock()
    order.status = MagicMock()
    order.status.__str__ = lambda s: "filled"
    order.filled_qty = "10"
    order.filled_avg_price = "150.25"
    order.symbol = "AAPL"
    order.side = MagicMock()
    order.side.__str__ = lambda s: "buy"
    mock_client.get_order_by_id.return_value = order

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        result = get_order_status("order-123", api_key="key", secret="secret", paper=True)

    assert result["status"] == "filled"
    assert result["filled_qty"] == 10
    assert result["filled_avg_price"] == pytest.approx(150.25)
    assert result["symbol"] == "AAPL"
    assert result["direction"] == "BUY"
