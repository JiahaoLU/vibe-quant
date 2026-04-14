# Cancel-Then-Reorder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent double-ordering when fills lag the bar interval by enforcing at most one open order per symbol at the execution layer — cancelling any stale open order before submitting a new one.

**Architecture:** Add a `cancel_order` pure function to `external/alpaca.py`. Modify `AlpacaPaperExecutionHandler.execute_order` to cancel any existing `_pending_orders` entry for the same symbol before submitting. `AlpacaExecutionHandler` inherits this fix for free (it subclasses `AlpacaPaperExecutionHandler` with only `_PAPER = False`). The portfolio (`SimplePortfolio`) is not touched — delta stays `target - holdings` against confirmed fills only.

**Tech Stack:** Python 3.10+, alpaca-py SDK (`TradingClient.cancel_order_by_id`), pytest, pytest-asyncio

---

## File Map

| File | Change |
|---|---|
| `external/alpaca.py` | Add `cancel_order(order_id, api_key, secret, paper)` |
| `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py` | Modify `execute_order` to cancel stale open orders before submitting |
| `tests/test_alpaca_execution_handlers.py` | Add three new tests |
| `tests/test_alpaca_external.py` | Add one test for `cancel_order` |

---

### Task 1: Add `cancel_order` to `external/alpaca.py`

**Files:**
- Modify: `external/alpaca.py`
- Test: `tests/test_alpaca_external.py`

- [ ] **Step 1: Write the failing test**

Open `tests/test_alpaca_external.py` and add at the bottom:

```python
def test_cancel_order_calls_client():
    from unittest.mock import MagicMock, patch
    from external.alpaca import cancel_order

    mock_client = MagicMock()

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_order("ord-42", "key", "secret", paper=True)

    mock_client.cancel_order_by_id.assert_called_once_with("ord-42")


def test_cancel_order_logs_and_continues_on_failure():
    from unittest.mock import MagicMock, patch
    from external.alpaca import cancel_order

    mock_client = MagicMock()
    mock_client.cancel_order_by_id.side_effect = RuntimeError("broker down")

    with patch("external.alpaca.TradingClient", return_value=mock_client):
        cancel_order("ord-99", "key", "secret", paper=False)  # must not raise
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alpaca_external.py::test_cancel_order_calls_client tests/test_alpaca_external.py::test_cancel_order_logs_and_continues_on_failure -v
```

Expected: `FAILED` — `ImportError` or `AttributeError` because `cancel_order` does not exist yet.

- [ ] **Step 3: Implement `cancel_order` in `external/alpaca.py`**

Add after the `cancel_all_open_orders` function (around line 192):

```python
def cancel_order(order_id: str, api_key: str, secret: str, paper: bool) -> None:
    """Cancel a single open order by ID. Logs and continues on failure."""
    client = TradingClient(api_key, secret, paper=paper)
    try:
        client.cancel_order_by_id(order_id)
        logger.info("Cancelled order %s", order_id)
    except Exception as exc:
        logger.warning("cancel_order %s failed: %s", order_id, exc)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alpaca_external.py::test_cancel_order_calls_client tests/test_alpaca_external.py::test_cancel_order_logs_and_continues_on_failure -v
```

Expected: both `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add external/alpaca.py tests/test_alpaca_external.py
git commit -m "feat: add cancel_order helper to external/alpaca.py"
```

---

### Task 2: Enforce one-open-order-per-symbol in `execute_order`

**Files:**
- Modify: `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py`
- Test: `tests/test_alpaca_execution_handlers.py`

- [ ] **Step 1: Write the failing tests**

Open `tests/test_alpaca_execution_handlers.py` and add at the bottom:

```python
def test_execute_order_cancels_existing_open_order_for_same_symbol():
    """New BUY for AAPL while a BUY for AAPL is already pending → cancel old, submit new."""
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from unittest.mock import patch

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-old"] = ("AAPL", "BUY", 100)

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order"
        ) as mock_cancel,
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-new",
        ) as mock_submit,
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_cancel.assert_called_once_with("ord-old", "k", "s", True)
    mock_submit.assert_called_once()
    assert "ord-old" not in handler._pending_orders
    assert "ord-new" in handler._pending_orders


def test_execute_order_does_not_cancel_order_for_different_symbol():
    """Pending order for MSFT must not be cancelled when a new order for AAPL arrives."""
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from unittest.mock import patch

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-msft"] = ("MSFT", "BUY", 50)

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order"
        ) as mock_cancel,
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-aapl",
        ),
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_cancel.assert_not_called()
    assert "ord-msft" in handler._pending_orders
    assert "ord-aapl" in handler._pending_orders


def test_execute_order_cancel_failure_still_submits_new_order():
    """If cancel_order raises, execute_order still submits the new order."""
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from unittest.mock import patch

    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    handler._pending_orders["ord-old"] = ("AAPL", "BUY", 100)

    with (
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.cancel_order",
            side_effect=RuntimeError("network error"),
        ),
        patch(
            "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
            return_value="ord-new",
        ) as mock_submit,
    ):
        handler.execute_order(_order(symbol="AAPL", direction="BUY", qty=100))

    mock_submit.assert_called_once()
    assert "ord-new" in handler._pending_orders
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alpaca_execution_handlers.py::test_execute_order_cancels_existing_open_order_for_same_symbol tests/test_alpaca_execution_handlers.py::test_execute_order_does_not_cancel_order_for_different_symbol tests/test_alpaca_execution_handlers.py::test_execute_order_cancel_failure_still_submits_new_order -v
```

Expected: all three `FAILED` — `cancel_order` is not yet imported or called.

- [ ] **Step 3: Implement the cancel-then-reorder logic**

In `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py`, update the import line and `execute_order`:

```python
from external.alpaca import TERMINAL_ORDER_STATUSES, cancel_order, get_order_status, open_fill_stream, submit_order
```

Replace the existing `execute_order` method body:

```python
def execute_order(self, event: OrderEvent) -> None:
    if event.direction == "HOLD":
        self._emit(FillEvent(
            symbol=event.symbol, timestamp=event.timestamp,
            direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
        ))
        return

    # Enforce one open order per symbol: cancel any stale open order before submitting.
    for order_id, (symbol, _direction, _qty) in list(self._pending_orders.items()):
        if symbol == event.symbol:
            cancel_order(order_id, self._api_key, self._secret, self._PAPER)
            self._pending_orders.pop(order_id, None)

    order_id = submit_order(
        symbol=event.symbol,
        direction=event.direction,
        quantity=event.quantity,
        api_key=self._api_key,
        secret=self._secret,
        paper=self._PAPER,
    )
    self._pending_orders[order_id] = (event.symbol, event.direction, event.quantity)
```

Note: the loop removes all matching entries defensively. Under the invariant being established there will be at most one, but iterating all guards against any pre-existing drift.

- [ ] **Step 4: Run the new tests to verify they pass**

```bash
pytest tests/test_alpaca_execution_handlers.py::test_execute_order_cancels_existing_open_order_for_same_symbol tests/test_alpaca_execution_handlers.py::test_execute_order_does_not_cancel_order_for_different_symbol tests/test_alpaca_execution_handlers.py::test_execute_order_cancel_failure_still_submits_new_order -v
```

Expected: all three `PASSED`.

- [ ] **Step 5: Run the full execution handler test suite to check for regressions**

```bash
pytest tests/test_alpaca_execution_handlers.py -v
```

Expected: all existing tests still `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add trading/impl/live_execution_handler/alpaca_paper_execution_handler.py tests/test_alpaca_execution_handlers.py
git commit -m "fix: cancel stale open order before submitting new order for same symbol"
```

---

### Task 3: Full regression sweep

**Files:** (read-only — no changes)

- [ ] **Step 1: Run the full test suite**

```bash
pytest --tb=short -q
```

Expected: all tests pass. If any test fails, read the failure message — do not guess the fix. The most likely failure is a test that patches `submit_order` but not `cancel_order` and now sees an unexpected import. If so, add `patch("...cancel_order")` alongside the existing `submit_order` patch in that test.

- [ ] **Step 2: Commit if any test fixes were needed**

Only commit if step 1 required changes:

```bash
git add <files touched>
git commit -m "fix: patch cancel_order in tests that patch submit_order"
```
