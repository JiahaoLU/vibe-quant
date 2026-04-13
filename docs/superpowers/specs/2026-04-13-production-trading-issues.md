# Production Trading Issues Audit — 2026-04-13

Audit of the live trading stack (`LiveRunner`, `AlpacaDataHandler`, `AlpacaPaperExecutionHandler`, `SimplePortfolio`, `RiskGuard`, `AlpacaReconciler`) for issues that can break production-level trading.

---

## Issue 1 — No order state reconciliation on restart

**Severity: Critical**

`_pending_orders` in `AlpacaPaperExecutionHandler` is in-memory only. After any crash or restart, all submitted-but-unfilled orders vanish from the dict. `AlpacaReconciler.hydrate()` restores positions and cash only — not open orders (`external/alpaca.py` only calls `get_positions` and `get_account`).

When those orders fill on the broker side post-restart, `_bridge_ws` in `fill_stream()` silently drops them because the order ID is no longer in `_pending_orders` (the symbol-membership guard `fill.symbol in {s for s, _, _ in self._pending_orders.values()}` passes, but `self._pending_orders.pop(str(data.order.id), None)` is a no-op). Portfolio-broker state divergence is permanent and compounds with every subsequent rebalance.

**Affected files:** `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py`, `trading/impl/position_reconciler/alpaca_reconciler.py`, `external/alpaca.py`

---

## Issue 2 — Rejected and cancelled orders never cleared from `_pending_orders`

**Severity: Critical**

`_poll_fallback` in `AlpacaPaperExecutionHandler` only acts on `status == "filled"`. Rejected, cancelled, and expired orders remain in `_pending_orders` indefinitely. On every subsequent bar, `fill_pending_orders` in `SimplePortfolio` computes `delta = target_qty - self._holdings[symbol]` against stale holdings (the shares were never acquired) and emits a fresh buy order. This creates a runaway order loop until the position is finally (accidentally) filled or the process is restarted.

**Affected files:** `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py` (line 64–79), `trading/impl/portfolio/simple_portfolio.py` (line 87–99)

---

## Issue 3 — No historical bar pre-loading at startup

**Severity: High**

`AlpacaDataHandler` starts with empty deques (`max_history=200`). `fetch_bars` retrieves only the last 3 days of daily bars (`start = now - timedelta(days=3)`) or 60 minutes of intraday bars (`start = now - timedelta(minutes=60)`) on each call. Only the most recent bar (`bars[-1]`) is appended to the deque per call.

Any strategy with a lookback window longer than the initial fetch window — moving averages, volatility estimators, momentum lookbacks — fires live signals on insufficient history from the moment the runner starts. There is no backfill step on startup, so for a 200-day moving average strategy, the first ~200 trading days of live operation produce incorrect signals.

**Affected files:** `trading/impl/data_handler/alpaca_data_handler.py` (lines 56–98), `external/alpaca.py` `fetch_bars` (line 54 — `bar = bars[-1]`)

---

## Issue 4 — RiskGuard daily loss limit is inactive on session day 1

**Severity: High**

`RiskGuard._day_open_equity` initializes to `None`. The auto-reset inside `check()` only fires when a **new** calendar date is detected from two consecutive events — it never fires on the very first event of a session. `reset_day()` is defined but never called anywhere in `LiveRunner` or `run_live.py`.

On the first trading day after any startup (including the deployment day), `_day_open_equity` remains `None`, the daily loss limit condition is never evaluated, and the guard returns the signal bundle unchanged regardless of intraday loss. The loss limit is therefore disabled during the highest-risk period: initial deployment and post-restart recovery.

**Affected files:** `trading/impl/risk_guard/risk_guard.py` (lines 33, 46–50), `trading/live_runner.py` (no `reset_day` call), `run_live.py` (no `reset_day` call)

---

## Issue 5 — Double-ordering when fills lag the bar interval (intraday)

**Severity: High**

For intraday bar frequencies (e.g. `5m`), if a submitted market order takes longer than one bar interval to fill — due to low liquidity, a halted symbol, or broker latency — the next `BarBundleEvent` fires before `on_fill` has updated `self._holdings`. `fill_pending_orders` computes `delta = target_qty - self._holdings[symbol]` against the pre-fill state and emits a second order for the same shares.

There is no "orders in flight" guard in `SimplePortfolio` and no idempotency check in `AlpacaPaperExecutionHandler.execute_order`. For a target of 100 shares that fills slowly, the system can accumulate 200 or 300 shares before any fill arrives, doubling or tripling intended exposure.

**Affected files:** `trading/impl/portfolio/simple_portfolio.py` (lines 86–103), `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py` (lines 30–45), `trading/live_runner.py` `_dispatch` (lines 92–102)
