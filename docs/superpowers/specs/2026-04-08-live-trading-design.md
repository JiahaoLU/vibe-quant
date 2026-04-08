# Live Trading Design

**Date:** 2026-04-08
**Status:** Approved

## Overview

Extend the existing event-driven backtesting engine to support live trading via Alpaca. Two modes:

- **Paper mode** — real-time data, signals, and portfolio tracking; orders routed to Alpaca's paper API (no real capital)
- **Live mode** — identical pipeline; orders routed to Alpaca's live API with real fills

The only wiring difference between modes is the `ExecutionHandler` injected at startup.

---

## File Layout

```
external/
  alpaca.py                            # thin wrappers over alpaca-py (REST + WebSocket)
                                       # pure functions, no state, no trading/ imports

trading/
  base/
    data.py                            # + update_bars_async() default implementation
    execution.py                       # + execute_order_async() default implementation
    portfolio.py                       # + restore(holdings, cash) abstract method
    live/
      __init__.py
      runner.py                        # LiveRunner ABC
      risk_guard.py                    # RiskGuard ABC
      reconciler.py                    # PositionReconciler ABC
      execution.py                     # LiveExecutionHandler ABC (adds fill_stream())

  impl/
    alpaca_data_handler.py             # overrides update_bars_async(); owns bar timing
    alpaca_paper_execution_handler.py  # routes to Alpaca paper trading API
    alpaca_execution_handler.py        # routes to Alpaca live API + WebSocket fill stream
    alpaca_reconciler.py               # hydrates portfolio from Alpaca /positions + /account
    live_runner.py                     # concrete LiveRunner — asyncio loop, broker-agnostic
    risk_guard.py                      # concrete RiskGuard — daily loss limit + per-symbol cap
    simple_portfolio.py                # + restore() implementation + optional risk_guard param

run_live.py                            # wiring point (mirrors run_backtest.py)
```

---

## Module Boundaries

- `external/alpaca.py` — wraps `alpaca-py` SDK. Provides plain functions: `fetch_bars()`, `submit_order()`, `get_positions()`, `get_account()`, `open_fill_stream()`. No state, no classes, no `trading/` imports.
- `trading/impl/alpaca_*.py` — call `external/alpaca.py` functions only. Never import `alpaca-py` directly.
- `trading/base/live/` — ABCs only. No Alpaca imports, no business logic.
- `trading/impl/live_runner.py` and `trading/impl/risk_guard.py` — broker-agnostic. Injected with Alpaca-specific components at wiring time.

---

## ABC Extensions

### `DataHandler` (`trading/base/data.py`)

```python
async def update_bars_async(self) -> bool:
    """Default: wraps update_bars() via asyncio.to_thread. Override for real async."""
    return await asyncio.to_thread(self.update_bars)
```

Existing handlers (`MultiCSVDataHandler`, `YahooDataHandler`) inherit this default — no changes needed.

### `ExecutionHandler` (`trading/base/execution.py`)

```python
async def execute_order_async(self, event: OrderEvent) -> None:
    """Default: wraps execute_order() via asyncio.to_thread. Override for real async."""
    await asyncio.to_thread(self.execute_order, event)
```

### `Portfolio` (`trading/base/portfolio.py`)

```python
@abstractmethod
def restore(self, holdings: dict[str, int], cash: float) -> None:
    """Hydrate portfolio state from an external source (e.g. broker reconciliation)."""
    ...
```

`SimplePortfolio.restore()` sets `self._holdings` and `self._cash` directly.

### New ABCs (`trading/base/live/`)

**`LiveRunner`** — `async def run() -> None`. Constructor: `(events, data, strategy, portfolio, execution: LiveExecutionHandler, reconciler)`.

**`RiskGuard`** — `def check(event: StrategyBundleEvent) -> StrategyBundleEvent | None`  
Returns the event unchanged if within limits, `None` if rejected.

**`PositionReconciler`** — `async def hydrate(portfolio: Portfolio) -> None`  
Queries broker state and calls `portfolio.restore(...)`.

**`LiveExecutionHandler`** (extends `ExecutionHandler`) — adds `fill_stream() -> AsyncContextManager`. `AlpacaPaperExecutionHandler` and `AlpacaExecutionHandler` both subclass this. `LiveRunner` types its `execution` parameter as `LiveExecutionHandler`.

---

## `SimplePortfolio` Changes

Two additions only — no logic changes:

1. `__init__` gains `risk_guard: RiskGuard | None = None`. Stored as `self._risk_guard`.
2. `on_signal()` calls `risk_guard.check(event)` before storing `_pending_signals`. If the guard returns `None`, the signal is dropped and logged.
3. `restore(holdings, cash)` sets `self._holdings = dict(holdings)` and `self._cash = cash`.

---

## `AlpacaDataHandler`

- Constructor params: `emit`, `symbols`, `bar_freq` (`"1d"` or `"5m"`, etc.), Alpaca credentials.
- `update_bars_async()`:
  - **Daily (`1d`)**: `await` sleep until 4:05 PM ET, fetch prior session OHLCV via `external.alpaca.fetch_bars()`, emit `BarBundleEvent`, return `True`. Return `False` if called outside session hours after market close.
  - **Intraday**: `await` sleep until next N-minute boundary, fetch completed bar, emit, return `True`.
- `get_latest_bars()` returns from the same internal deque used by backtest handlers — interface is identical.

---

## `AlpacaPaperExecutionHandler` and `AlpacaExecutionHandler`

Both subclass `ExecutionHandler`. Identical interface — only the Alpaca base URL differs (paper vs live credentials).

`execute_order()` (synchronous):
1. Calls `external.alpaca.submit_order()` with direction, quantity, symbol.
2. Returns immediately — does not wait for fill.

Fill arrival (asynchronous):
- `fill_stream()` is an async context manager that opens the Alpaca trade update WebSocket via `external.alpaca.open_fill_stream()`.
- On each fill event received, translates to `FillEvent` and puts it on the shared queue.
- On WebSocket disconnect, falls back to polling `/orders/{id}` every 3 seconds until filled.
- `LiveRunner` owns the stream lifecycle (opens it, passes it to a background task).

---

## `AlpacaReconciler`

`hydrate(portfolio)`:
1. Calls `external.alpaca.get_positions()` → `dict[str, int]` (symbol → qty).
2. Calls `external.alpaca.get_account()` → `float` (cash).
3. Calls `portfolio.restore(holdings, cash)`.

Called once at `LiveRunner` startup before the first bar.

---

## `RiskGuard` (concrete, `trading/impl/risk_guard.py`)

Constructor params: `max_daily_loss_pct: float`, `max_position_pct: float`.

`check(event: StrategyBundleEvent) -> StrategyBundleEvent | None`:
- **Daily loss limit**: if current equity < day-open equity × (1 - max_daily_loss_pct), return `None` and log warning.
- **Per-symbol cap**: for each signal in the bundle, if `signal × initial_capital / price > max_position_pct × current_equity`, clamp the signal weight to the cap.
- Returns (possibly modified) event, or `None` if trading is halted.

`RiskGuard` receives at construction:
- `get_equity: Callable[[], float]` — current portfolio equity
- `get_day_open_equity: Callable[[], float]` — equity at market open (set by `LiveRunner` at session start)
- `get_bars: Callable[[str, int], list[TickEvent]]` — for price lookup in per-symbol cap calculation

All three are injected from portfolio/data references at wiring time in `run_live.py`.

---

## `LiveRunner` (concrete, `trading/impl/live_runner.py`)

```python
class LiveRunner(LiveRunnerBase):
    async def run(self) -> None:
        await self._reconciler.hydrate(self._portfolio)
        async with self._execution.fill_stream() as stream:
            asyncio.create_task(self._drain_fill_stream(stream))
            while not self._shutdown:
                bar_ready = await self._data.update_bars_async()
                if not bar_ready:
                    break
                while not self._events.empty():
                    event = self._events.get_nowait()
                    self._dispatch(event)

    def _dispatch(self, event):
        match event.type:
            case EventType.BAR_BUNDLE:
                self._portfolio.fill_pending_orders(event)
                self._strategy.get_signals(event)
            case EventType.STRATEGY_BUNDLE:
                self._portfolio.on_signal(event)
            case EventType.ORDER:
                self._execution.execute_order(event)
            case EventType.FILL:
                self._portfolio.on_fill(event)
```

`_drain_fill_stream` reads from the WebSocket stream and puts `FillEvent` objects on the queue. `SIGTERM`/`KeyboardInterrupt` sets `self._shutdown = True`.

---

## `run_live.py`

```python
MODE = "paper"  # "paper" | "live"

events   = queue.Queue()
strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
# ... load strategies from params registry (same as run_backtest.py) ...

data = AlpacaDataHandler(events.put, symbols, bar_freq="1d",
                         api_key=API_KEY, secret=API_SECRET)

execution = (
    AlpacaPaperExecutionHandler(events.put, api_key=PAPER_KEY, secret=PAPER_SECRET)
    if MODE == "paper"
    else AlpacaExecutionHandler(events.put, api_key=LIVE_KEY, secret=LIVE_SECRET)
)

risk_guard  = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20)
reconciler  = AlpacaReconciler(api_key=..., secret=...)
portfolio   = SimplePortfolio(events.put, data.get_latest_bars, symbols,
                              risk_guard=risk_guard,
                              initial_capital=INITIAL_CAPITAL, ...)

runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
asyncio.run(runner.run())
```

Credentials loaded from environment variables, not hardcoded.

---

## What Does Not Change

- `Backtester`, `StrategyContainer`, all `Strategy` subclasses — zero changes
- `SimulatedExecutionHandler` — unchanged, still used by `run_backtest.py`
- `MultiCSVDataHandler`, `YahooDataHandler` — unchanged, inherit async default
- All existing event dataclasses — unchanged
- `run_backtest.py` — unchanged

---

## Out of Scope

- Order types other than MARKET (limit orders, brackets)
- Short selling (already prohibited by `SimplePortfolio`)
- Multi-account or multi-broker routing
- Live result writing / dashboard (use existing `plot_results.ipynb` for paper mode analysis)
