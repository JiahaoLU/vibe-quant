# Trade Logger Design

**Date:** 2026-04-15
**Scope:** Paper and live trading only — not backtest.

## Goal

Log every signal decision, order intent, and fill execution to a persistent SQLite database for audit and post-trade analysis. Every trade is traceable from strategy signal → order → fill via a shared `order_id`.

---

## Data Model Changes (`trading/events.py`)

Two new fields:

- `OrderEvent.order_id: str` — UUID4 generated in `SimplePortfolio._emit_order` via `str(uuid.uuid4())`. HOLD orders receive an empty string and are not logged.
- `FillEvent.order_id: str` — echoed back from the execution handler. For Alpaca, read from `data.order.client_order_id` in `_translate` and the poll fallback. For `SimulatedExecutionHandler`, copied directly from the incoming `OrderEvent`. HOLD fills receive an empty string and are not logged.

`external/alpaca.py` — `submit_order` gains a `client_order_id: str` parameter, passed to `MarketOrderRequest(client_order_id=client_order_id, ...)`. The broker stores it and echoes it back in fill stream events as `data.order.client_order_id`.

---

## TradeLogger ABC (`trading/base/live/trade_logger.py`)

```python
class TradeLogger(ABC):
    @abstractmethod
    def open_session(self, session_id: str, mode: str, strategy_names: list[str]) -> None: ...

    @abstractmethod
    def log_signal(self, session_id: str, event: StrategyBundleEvent) -> None: ...

    @abstractmethod
    def log_order(self, session_id: str, event: OrderEvent) -> None: ...

    @abstractmethod
    def log_fill(self, session_id: str, event: FillEvent) -> None: ...

    @abstractmethod
    def close_session(self, session_id: str) -> None: ...
```

---

## SQLite Implementation (`trading/impl/trade_logger/sqlite_trade_logger.py`)

Single database file (default: `logs/trades.db`), path configurable at construction. All sessions append to it; a `session_id` column distinguishes runs.

### Schema

**`sessions`**
| Column | Type | Notes |
|---|---|---|
| `session_id` | TEXT PK | UUID4 |
| `started_at` | TEXT | ISO-8601 UTC |
| `ended_at` | TEXT | ISO-8601 UTC, NULL until session closes |
| `mode` | TEXT | `"paper"` or `"live"` |
| `strategy_names` | TEXT | JSON array of strategy class names |

**`signals`**
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `session_id` | TEXT | FK → sessions |
| `timestamp` | TEXT | ISO-8601 UTC |
| `strategy_id` | TEXT | from `StrategyBundleEvent.per_strategy` keys |
| `symbol` | TEXT | |
| `weight` | REAL | fractional weight from strategy |

One row per (strategy, symbol) pair per bar. Expands `StrategyBundleEvent.per_strategy`.

**`orders`**
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `session_id` | TEXT | FK → sessions |
| `order_id` | TEXT UNIQUE | UUID4 from `OrderEvent.order_id` |
| `timestamp` | TEXT | ISO-8601 UTC |
| `symbol` | TEXT | |
| `direction` | TEXT | `"BUY"` or `"SELL"` |
| `quantity` | INTEGER | |
| `reference_price` | REAL | next bar open used for sizing |

**`fills`**
| Column | Type | Notes |
|---|---|---|
| `id` | INTEGER PK | autoincrement |
| `session_id` | TEXT | FK → sessions |
| `order_id` | TEXT | FK → orders.order_id |
| `timestamp` | TEXT | ISO-8601 UTC |
| `symbol` | TEXT | |
| `direction` | TEXT | `"BUY"` or `"SELL"` |
| `quantity` | INTEGER | actual filled quantity |
| `fill_price` | REAL | |
| `commission` | REAL | |

An order with no matching fill row = unfilled or rejected.

---

## LiveRunner Wiring (`trading/live_runner.py`)

`LiveRunner.__init__` gains:
```python
trade_logger: TradeLogger | None = None
```

At `run()` start:
- `session_id = str(uuid.uuid4())`
- `trade_logger.open_session(session_id, mode, strategy.strategy_ids)`

`mode` is a new `str` parameter on `LiveRunner.__init__` (values: `"paper"` or `"live"`), set in `run_live.py`.

`strategy.strategy_ids` requires adding a public `strategy_ids: list[str]` property to `StrategyContainer` (exposing the existing `self._ids`). The `StrategySignalGenerator` ABC should also gain this as an abstract property.

In `_dispatch`, before routing to handlers:
```
STRATEGY_BUNDLE → trade_logger.log_signal(session_id, event)
ORDER           → trade_logger.log_order(session_id, event)   # skip direction == "HOLD"
FILL            → trade_logger.log_fill(session_id, event)    # skip direction == "HOLD"
```

In the `finally` block of `run()`:
- `trade_logger.close_session(session_id)` — writes `ended_at`

---

## Wiring in `run_live.py`

```python
from trading.impl.trade_logger import SqliteTradeLogger

trade_logger = SqliteTradeLogger(db_path="logs/trades.db")

runner = LiveRunner(
    ...,
    trade_logger=trade_logger,
    mode=MODE,   # "paper" or "live"
)
```

---

## Files Changed / Added

| File | Change |
|---|---|
| `trading/events.py` | Add `order_id: str` to `OrderEvent` and `FillEvent` |
| `trading/impl/portfolio/simple_portfolio.py` | Generate UUID4 in `_emit_order` |
| `external/alpaca.py` | Add `client_order_id` param to `submit_order` |
| `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py` | Echo `client_order_id` into `FillEvent`; pass it to `submit_order` |
| `trading/base/live/trade_logger.py` | New ABC |
| `trading/base/strategy.py` | Add abstract `strategy_ids` property to `StrategySignalGenerator` |
| `trading/impl/strategy_signal_generator/strategy_container.py` | Expose `strategy_ids` property |
| `trading/impl/trade_logger/__init__.py` | New |
| `trading/impl/trade_logger/sqlite_trade_logger.py` | New concrete impl |
| `trading/live_runner.py` | Inject `trade_logger`, `mode`; call log methods at dispatch |
| `run_live.py` | Construct and wire `SqliteTradeLogger` |
