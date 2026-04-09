import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_hydrate_calls_portfolio_restore_with_broker_state():
    from trading.impl.position_reconciler.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()

    with (
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_positions", return_value={"AAPL": 5, "MSFT": 2}),
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_account",   return_value=8_500.0),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_portfolio.restore.assert_called_once_with(
        holdings={"AAPL": 5, "MSFT": 2},
        cash=8_500.0,
    )


def test_hydrate_calls_restore_with_empty_positions():
    from trading.impl.position_reconciler.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()

    with (
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_positions", return_value={}),
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_account",   return_value=10_000.0),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_portfolio.restore.assert_called_once_with(holdings={}, cash=10_000.0)
