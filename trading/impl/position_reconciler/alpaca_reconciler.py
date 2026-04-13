import logging

from ...base.live.reconciler import PositionReconciler
from ...base.portfolio import Portfolio
from external.alpaca import cancel_all_open_orders, get_account, get_positions

logger = logging.getLogger(__name__)


class AlpacaReconciler(PositionReconciler):
    """Hydrates portfolio state from Alpaca's /positions and /account endpoints.

    On startup, cancels all open orders before reading positions so the
    portfolio restores from a clean broker state.
    """

    def __init__(self, api_key: str, secret: str, paper: bool):
        self._api_key = api_key
        self._secret  = secret
        self._paper   = paper

    async def hydrate(self, portfolio: Portfolio) -> None:
        cancel_all_open_orders(self._api_key, self._secret, self._paper)
        holdings = get_positions(self._api_key, self._secret, self._paper)
        cash     = get_account(self._api_key,   self._secret, self._paper)
        logger.info("Reconciled: %d positions, cash=%.2f", len(holdings), cash)
        portfolio.restore(holdings=holdings, cash=cash)
