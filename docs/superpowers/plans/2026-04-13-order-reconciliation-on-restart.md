# Order Reconciliation on Restart Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cancel all open broker orders during startup reconciliation so that stale pre-crash orders never cause portfolio-broker state divergence after a restart.

**Architecture:** On startup, `AlpacaReconciler.hydrate()` calls a new `cancel_all_open_orders()` wrapper in `external/alpaca.py` before fetching positions and cash. This is a clean-slate approach: any order that was open before the crash was placed on pre-crash strategy state, which is now stale. Cancelling them lets the next bar re-derive fresh orders from reconciled positions.

**Tech Stack:** `alpaca-py` `TradingClient.cancel_orders()`, Python `asyncio`, `unittest.mock`

---

## File Structure

| File | Change |
|---|---|
| `external/alpaca.py` | Add `cancel_all_open_orders(api_key, secret, paper) → None` |
| `trading/impl/position_reconciler/alpaca_reconciler.py` | Import and call `cancel_all_open_orders` at top of `hydrate()` |
| `tests/test_alpaca_external.py` | Add test for `cancel_all_open_orders` |
| `tests/test_alpaca_reconciler.py` | Add test that cancel is called before positions are fetched |

---

### Task 1: `cancel_all_open_orders` in `external/alpaca.py`

**Files:**
- Modify: `external/alpaca.py`
- Test: `tests/test_alpaca_external.py`

- [ ] **Step 1: Write the failing test**

Add to the bottom of `tests/test_alpaca_external.py`:

```python
def test_cancel_all_open_orders_calls_sdk_cancel():
    from external.alpaca import cancel_all_open_orders

    mock_client = MagicMock()
    mock_client.cancel_orders.return_value = [MagicMock(), MagicMock()]

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_all_open_orders(api_key="key", secret="secret", paper=True)

    mock_client.cancel_orders.assert_called_once()


def test_cancel_all_open_orders_no_open_orders():
    from external.alpaca import cancel_all_open_orders

    mock_client = MagicMock()
    mock_client.cancel_orders.return_value = []

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_all_open_orders(api_key="key", secret="secret", paper=True)

    mock_client.cancel_orders.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_alpaca_external.py::test_cancel_all_open_orders_calls_sdk_cancel tests/test_alpaca_external.py::test_cancel_all_open_orders_no_open_orders -v
```

Expected: `FAILED` with `ImportError: cannot import name 'cancel_all_open_orders'`

- [ ] **Step 3: Implement `cancel_all_open_orders` in `external/alpaca.py`**

Add this function after `get_order_status` (before `open_fill_stream`) in `external/alpaca.py`:

```python
def cancel_all_open_orders(api_key: str, secret: str, paper: bool) -> None:
    """Cancel all open orders at the broker.
    Called on startup so stale pre-crash orders never diverge from portfolio state."""
    client = TradingClient(api_key, secret, paper=paper)
    client.cancel_orders()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alpaca_external.py::test_cancel_all_open_orders_calls_sdk_cancel tests/test_alpaca_external.py::test_cancel_all_open_orders_no_open_orders -v
```

Expected: both `PASSED`

- [ ] **Step 5: Run full external test suite to check for regressions**

```bash
pytest tests/test_alpaca_external.py -v
```

Expected: all existing tests still `PASSED`

- [ ] **Step 6: Commit**

```bash
git add external/alpaca.py tests/test_alpaca_external.py
git commit -m "feat: add cancel_all_open_orders to external/alpaca.py"
```

---

### Task 2: Call `cancel_all_open_orders` in `AlpacaReconciler.hydrate()`

**Files:**
- Modify: `trading/impl/position_reconciler/alpaca_reconciler.py`
- Test: `tests/test_alpaca_reconciler.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_alpaca_reconciler.py`:

```python
def test_hydrate_cancels_open_orders_before_restoring_positions():
    """Cancel must happen before positions are read — otherwise we might read
    a partially-filled state that the cancelled order was about to change."""
    import asyncio
    from unittest.mock import MagicMock, patch
    from trading.impl.position_reconciler.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()
    call_order = []

    with (
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.cancel_all_open_orders",
            side_effect=lambda *a, **kw: call_order.append("cancel"),
        ) as mock_cancel,
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.get_positions",
            side_effect=lambda *a, **kw: call_order.append("positions") or {"AAPL": 5},
        ),
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.get_account",
            return_value=8_500.0,
        ),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_cancel.assert_called_once_with(api_key="key", secret="secret", paper=True)
    assert call_order == ["cancel", "positions"], (
        f"Expected cancel before positions, got: {call_order}"
    )


def test_hydrate_cancels_with_correct_credentials():
    import asyncio
    from unittest.mock import MagicMock, patch
    from trading.impl.position_reconciler.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="my-key", secret="my-secret", paper=False)
    mock_portfolio = MagicMock()

    with (
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.cancel_all_open_orders",
        ) as mock_cancel,
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.get_positions",
            return_value={},
        ),
        patch(
            "trading.impl.position_reconciler.alpaca_reconciler.get_account",
            return_value=10_000.0,
        ),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_cancel.assert_called_once_with(api_key="my-key", secret="my-secret", paper=False)
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alpaca_reconciler.py::test_hydrate_cancels_open_orders_before_restoring_positions tests/test_alpaca_reconciler.py::test_hydrate_cancels_with_correct_credentials -v
```

Expected: `FAILED` — `assert mock_cancel.call_count == 1` fails because `cancel_all_open_orders` is not yet imported or called.

- [ ] **Step 3: Update `alpaca_reconciler.py`**

Replace the full file content of `trading/impl/position_reconciler/alpaca_reconciler.py`:

```python
import logging

from ...base.live.reconciler import PositionReconciler
from ...base.portfolio import Portfolio
from external.alpaca import cancel_all_open_orders, get_account, get_positions

logger = logging.getLogger(__name__)


class AlpacaReconciler(PositionReconciler):
    """Hydrates portfolio state from Alpaca's /positions and /account endpoints.

    On startup, cancels all open orders before reading positions. This ensures
    the portfolio starts from a clean, unambiguous broker state — any order
    open before a crash was placed on stale pre-crash strategy state.
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
```

- [ ] **Step 4: Run new tests to verify they pass**

```bash
pytest tests/test_alpaca_reconciler.py::test_hydrate_cancels_open_orders_before_restoring_positions tests/test_alpaca_reconciler.py::test_hydrate_cancels_with_correct_credentials -v
```

Expected: both `PASSED`

- [ ] **Step 5: Run full reconciler test suite to check for regressions**

```bash
pytest tests/test_alpaca_reconciler.py -v
```

Expected: all `PASSED` — existing `test_hydrate_calls_portfolio_restore_with_broker_state` and `test_hydrate_calls_restore_with_empty_positions` still pass because `cancel_all_open_orders` is patched in those tests too (they don't mock it, so the real function would be called — update them below).

- [ ] **Step 6: Patch existing reconciler tests to mock `cancel_all_open_orders`**

The two existing tests in `tests/test_alpaca_reconciler.py` will now call `cancel_all_open_orders` for real (hitting the SDK) unless mocked. Update them:

```python
import asyncio
from unittest.mock import MagicMock, patch


def test_hydrate_calls_portfolio_restore_with_broker_state():
    from trading.impl.position_reconciler.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()

    with (
        patch("trading.impl.position_reconciler.alpaca_reconciler.cancel_all_open_orders"),
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
        patch("trading.impl.position_reconciler.alpaca_reconciler.cancel_all_open_orders"),
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_positions", return_value={}),
        patch("trading.impl.position_reconciler.alpaca_reconciler.get_account",   return_value=10_000.0),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_portfolio.restore.assert_called_once_with(holdings={}, cash=10_000.0)
```

Replace the full content of `tests/test_alpaca_reconciler.py` with the above two existing tests (updated) plus the two new tests from Step 1.

- [ ] **Step 7: Run full reconciler test suite one more time**

```bash
pytest tests/test_alpaca_reconciler.py -v
```

Expected: all 4 tests `PASSED`

- [ ] **Step 8: Run the full test suite**

```bash
pytest -v
```

Expected: all tests `PASSED` — no regressions anywhere else.

- [ ] **Step 9: Commit**

```bash
git add trading/impl/position_reconciler/alpaca_reconciler.py tests/test_alpaca_reconciler.py
git commit -m "fix: cancel all open orders on startup in AlpacaReconciler

Stale pre-crash orders in _pending_orders caused permanent portfolio-broker
divergence when they filled post-restart. Cancel all open orders before
reading positions so each startup begins from an unambiguous broker state.
The next bar re-derives and places fresh orders from reconciled holdings."
```

---

## Self-Review

**Spec coverage:**
- ✅ `_pending_orders` divergence after restart — fixed: open orders are cancelled before hydration, so there are no pre-crash orders to track
- ✅ `external/alpaca.py` needed a new wrapper — `cancel_all_open_orders` added
- ✅ `AlpacaReconciler.hydrate()` needed to call it — done, with ordering guarantee tested
- ✅ `AlpacaPaperExecutionHandler` — no change needed; `_pending_orders` starts empty (correct after cancellation)

**Placeholder scan:** None found. All steps contain complete code.

**Type consistency:** `cancel_all_open_orders(api_key, secret, paper)` signature is consistent across `external/alpaca.py`, the import in `alpaca_reconciler.py`, all test patches, and the call site.
