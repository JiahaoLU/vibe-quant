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


def test_fetch_bars_history_returns_all_bars_in_window():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()

    bar1 = _mock_bar("AAPL", c=100.5)
    bar1.timestamp = datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)
    bar2 = _mock_bar("AAPL", o=101.0, h=102.0, l=100.0, c=101.5, v=60000)
    bar2.timestamp = datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc)

    mock_bar_set.__getitem__ = lambda self, sym: [bar1, bar2]
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert "AAPL" in result
    assert len(result["AAPL"]) == 2
    assert result["AAPL"][0]["close"] == 100.5
    assert result["AAPL"][1]["close"] == 101.5
    assert result["AAPL"][0]["timestamp"] == datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)


def test_fetch_bars_history_returns_bars_sorted_by_timestamp():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()

    newer_bar = _mock_bar("AAPL", o=101.0, h=102.0, l=100.0, c=101.5, v=60000)
    newer_bar.timestamp = datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc)
    older_bar = _mock_bar("AAPL", c=100.5)
    older_bar.timestamp = datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)

    mock_bar_set.__getitem__ = lambda self, sym: [newer_bar, older_bar]
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert result["AAPL"][0]["timestamp"] < result["AAPL"][1]["timestamp"]


def test_fetch_bars_history_omits_symbol_with_no_bars():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()
    mock_bar_set.__getitem__ = lambda self, sym: []
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert result == {}


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


def test_cancel_all_open_orders_calls_sdk_cancel():
    from external.alpaca import cancel_all_open_orders

    mock_client = MagicMock()
    mock_client.cancel_orders.return_value = [MagicMock(), MagicMock()]

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_all_open_orders(api_key="key", secret="secret", paper=True)

    mock_client.cancel_orders.assert_called_once()


def test_cancel_all_open_orders_forwards_credentials():
    from external.alpaca import cancel_all_open_orders

    mock_client = MagicMock()

    with patch("external.alpaca.TradingClient", return_value=mock_client) as mock_tc:
        cancel_all_open_orders(api_key="my-key", secret="my-secret", paper=False)

    mock_tc.assert_called_once_with("my-key", "my-secret", paper=False)
    mock_client.cancel_orders.assert_called_once()


def test_cancel_all_open_orders_logs_warning_on_failure():
    from external.alpaca import cancel_all_open_orders

    mock_client = MagicMock()
    mock_client.cancel_orders.side_effect = RuntimeError("broker unavailable")

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        # must not raise — failure is non-fatal
        cancel_all_open_orders(api_key="key", secret="secret", paper=True)


def test_cancel_order_calls_client():
    from external.alpaca import cancel_order

    mock_client = MagicMock()

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_order("ord-42", "key", "secret", paper=True)

    mock_client.cancel_order_by_id.assert_called_once_with("ord-42")


def test_cancel_order_logs_and_continues_on_failure():
    from external.alpaca import cancel_order

    mock_client = MagicMock()
    mock_client.cancel_order_by_id.side_effect = RuntimeError("broker down")

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_order("ord-99", "key", "secret", paper=False)
