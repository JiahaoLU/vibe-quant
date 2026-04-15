# Trade Logger Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Log every signal, order, and fill in paper/live trading to a SQLite database with a shared `order_id` linking order→fill for audit and analysis.

**Architecture:** A `TradeLogger` ABC (injected into `LiveRunner`) intercepts `StrategyBundleEvent`, `OrderEvent`, and `FillEvent` at dispatch time. A `SqliteTradeLogger` concrete implementation appends to a single `logs/trades.db` file; each run is identified by a `session_id` UUID. Orders and fills are linked via a `client_order_id` UUID generated in `SimplePortfolio` and round-tripped through Alpaca's `client_order_id` field.

**Tech Stack:** Python 3.10+, `uuid` (stdlib), `sqlite3` (stdlib), `pytest`, `pytest-asyncio`

---

## File Map

| File | Action |
|---|---|
| `trading/events.py` | Add `order_id: str = ""` to `OrderEvent` and `FillEvent` |
| `trading/impl/portfolio/simple_portfolio.py` | Generate UUID4 in `_emit_order` for non-HOLD orders |
| `external/alpaca.py` | Add `client_order_id: str` param to `submit_order` |
| `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py` | Pass `order_id` to `submit_order`; store it in `_pending_orders`; echo it in `_translate` and poll fallback |
| `trading/base/strategy.py` | Add abstract `strategy_ids` property to `StrategySignalGenerator` |
| `trading/impl/strategy_signal_generator/strategy_container.py` | Expose `strategy_ids` property |
| `trading/base/live/trade_logger.py` | New ABC |
| `trading/impl/trade_logger/__init__.py` | New — exports `SqliteTradeLogger` |
| `trading/impl/trade_logger/sqlite_trade_logger.py` | New concrete SQLite implementation |
| `trading/live_runner.py` | Add `mode` and `trade_logger` params; call log methods at dispatch |
| `run_live.py` | Construct and wire `SqliteTradeLogger` |
| `tests/test_events.py` | Add tests for new `order_id` field |
| `tests/test_portfolio.py` | Add test that `_emit_order` sets a UUID `order_id` |
| `tests/test_alpaca_execution_handlers.py` | Update existing tests broken by `client_order_id`; add echo tests |
| `tests/test_strategy_container.py` | Add test for `strategy_ids` property |
| `tests/test_trade_logger.py` | New — full coverage of `SqliteTradeLogger` |
| `tests/test_live_runner.py` | Add tests for trade logger dispatch wiring |

---

### Task 1: Add `order_id` to `OrderEvent` and `FillEvent`

**Files:**
- Modify: `trading/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_events.py`:

```python
def test_order_event_order_id_defaults_to_empty_string():
    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
    )
    assert order.order_id == ""


def test_order_event_order_id_can_be_set():
    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
        order_id="abc-123",
    )
    assert order.order_id == "abc-123"


def test_fill_event_order_id_defaults_to_empty_string():
    fill = FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        direction="BUY", quantity=10, fill_price=100.0, commission=0.0,
    )
    assert fill.order_id == ""


def test_fill_event_order_id_can_be_set():
    fill = FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        direction="BUY", quantity=10, fill_price=100.0, commission=0.0,
        order_id="abc-123",
    )
    assert fill.order_id == "abc-123"
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_events.py::test_order_event_order_id_defaults_to_empty_string tests/test_events.py::test_order_event_order_id_can_be_set tests/test_events.py::test_fill_event_order_id_defaults_to_empty_string tests/test_events.py::test_fill_event_order_id_can_be_set -v
```

Expected: FAIL with `TypeError: __init__() got an unexpected keyword argument 'order_id'`

- [ ] **Step 3: Add `order_id` to both dataclasses**

In `trading/events.py`, add `order_id: str = ""` to `OrderEvent` after `bar_is_synthetic`:

```python
@dataclass
class OrderEvent(Event):
    symbol:          str
    timestamp:       datetime
    order_type:      Literal["MARKET", "LIMIT"]
    direction:       Literal["BUY", "SELL", "HOLD"]
    quantity:        int
    reference_price: float = 0.0
    bar_volume:      float = 0.0
    bar_high:        float = 0.0
    bar_low:         float = 0.0
    bar_close:       float = 0.0
    bar_is_synthetic: bool = False
    order_id:        str   = ""
    type: EventType = field(default=EventType.ORDER, init=False)
```

Add `order_id: str = ""` to `FillEvent` after `commission`:

```python
@dataclass
class FillEvent(Event):
    symbol:     str
    timestamp:  datetime
    direction:  Literal["BUY", "SELL", "HOLD"]
    quantity:   int
    fill_price: float
    commission: float
    order_id:   str   = ""
    type: EventType = field(default=EventType.FILL, init=False)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_events.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/events.py tests/test_events.py
git commit -m "feat: add order_id field to OrderEvent and FillEvent"
```

---

### Task 2: Generate UUID4 in `SimplePortfolio._emit_order`

**Files:**
- Modify: `trading/impl/portfolio/simple_portfolio.py`
- Test: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_portfolio.py`:

```python
import re

_UUID4_RE = re.compile(
    r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$'
)


def test_emit_order_sets_uuid4_order_id():
    """Every non-HOLD order emitted by the portfolio carries a valid UUID4 order_id."""
    collected = []
    ts = datetime(2020, 1, 3)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=100.0, high=100.0,
                     low=100.0, close=100.0, volume=1000.0)
    bar = BarBundleEvent(timestamp=ts, bars={"AAPL": tick})

    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)
    bundle = StrategyBundleEvent(timestamp=ts, combined={"AAPL": sig}, per_strategy={"s": {"AAPL": 1.0}})
    portfolio.on_signal(bundle)
    portfolio.fill_pending_orders(bar)

    orders = [e for e in collected if hasattr(e, "direction") and e.direction != "HOLD"]
    assert len(orders) == 1
    assert _UUID4_RE.match(orders[0].order_id), f"Expected UUID4, got: {orders[0].order_id!r}"


def test_hold_order_has_empty_order_id():
    """HOLD orders get an empty order_id."""
    collected = []
    ts = datetime(2020, 1, 3)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=100.0, high=100.0,
                     low=100.0, close=100.0, volume=1000.0)
    bar = BarBundleEvent(timestamp=ts, bars={"AAPL": tick})

    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    # No signal → HOLD order emitted
    portfolio.fill_pending_orders(bar)

    holds = [e for e in collected if hasattr(e, "direction") and e.direction == "HOLD"]
    assert len(holds) == 1
    assert holds[0].order_id == ""
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_portfolio.py::test_emit_order_sets_uuid4_order_id tests/test_portfolio.py::test_hold_order_has_empty_order_id -v
```

Expected: FAIL — `order_id` will be `""` for all orders (UUID not generated yet)

- [ ] **Step 3: Add UUID4 generation in `_emit_order`**

In `trading/impl/portfolio/simple_portfolio.py`, add `import uuid` at the top, then update `_emit_order`:

```python
import uuid
```

```python
def _emit_order(
    self,
    symbol: str,
    timestamp: datetime,
    direction: str,
    qty: int,
    bar: TickEvent | None = None,
) -> None:
    order = OrderEvent(
        symbol=symbol,
        timestamp=timestamp,
        order_type="MARKET",
        direction=direction,
        quantity=qty,
        order_id=str(uuid.uuid4()) if direction != "HOLD" else "",
    )
    if bar:
        order.reference_price  = bar.open
        order.bar_volume       = bar.volume
        order.bar_high         = bar.high
        order.bar_low          = bar.low
        order.bar_close        = bar.close
        order.bar_is_synthetic = bar.is_synthetic
    self._emit(order)
```

- [ ] **Step 4: Run tests to confirm they pass**

```
pytest tests/test_portfolio.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/portfolio/simple_portfolio.py tests/test_portfolio.py
git commit -m "feat: generate UUID4 order_id in SimplePortfolio._emit_order"
```

---

### Task 3: Pass `client_order_id` through the Alpaca execution handler

**Files:**
- Modify: `external/alpaca.py`
- Modify: `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py`
- Test: `tests/test_alpaca_execution_handlers.py`

- [ ] **Step 1: Write the new failing tests**

Add to `tests/test_alpaca_execution_handlers.py`:

```python
def test_execute_order_passes_client_order_id_to_submit():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2024, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
        order_id="my-uuid-123",
    )
    handler = AlpacaPaperExecutionHandler(emit=lambda e: None, api_key="k", secret="s")
    with patch(
        "trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order",
        return_value="broker-ord-1",
    ) as mock_sub:
        handler.execute_order(order)

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="k", secret="s", paper=True,
        client_order_id="my-uuid-123",
    )


@pytest.mark.asyncio
async def test_fill_stream_ws_echoes_client_order_id_in_fill():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from contextlib import asynccontextmanager

    raw_fill = MagicMock()
    raw_fill.event = MagicMock()
    raw_fill.event.__str__ = lambda s: "fill"
    raw_fill.order = MagicMock()
    raw_fill.order.id = "broker-ord-1"
    raw_fill.order.client_order_id = "my-uuid-123"
    raw_fill.order.symbol = "AAPL"
    raw_fill.order.side = MagicMock()
    raw_fill.order.side.__str__ = lambda s: "buy"
    raw_fill.order.filled_qty = "10"
    raw_fill.order.filled_avg_price = "150.50"

    ws_queue = asyncio.Queue()
    await ws_queue.put(raw_fill)

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    handler = AlpacaPaperExecutionHandler(emit=MagicMock(), api_key="k", secret="s")
    handler._pending_orders["broker-ord-1"] = ("AAPL", "BUY", 10, "my-uuid-123")

    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.order_id == "my-uuid-123"


@pytest.mark.asyncio
async def test_poll_fallback_echoes_client_order_id_in_fill():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from contextlib import asynccontextmanager

    ws_queue = asyncio.Queue()

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    handler._pending_orders["broker-ord-1"] = ("AAPL", "BUY", 5, "my-uuid-456")

    status_payload = {
        "status": "filled",
        "filled_qty": 5,
        "filled_avg_price": 150.0,
    }

    with (
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.open_fill_stream", _mock_stream),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.get_order_status", return_value=status_payload),
        patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler._POLL_INTERVAL", 0.05),
    ):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.order_id == "my-uuid-456"
```

- [ ] **Step 2: Update the two existing tests that assert `submit_order` call signature**

The existing `test_paper_execute_order_calls_submit_order` and `test_live_execute_order_calls_submit_order_with_paper_false` don't pass `order_id` to `_order()`, so `client_order_id` will be `""`. Update their assertions:

```python
def test_paper_execute_order_calls_submit_order():
    from trading.impl.live_execution_handler.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order", return_value="ord-1") as mock_sub:
        handler.execute_order(_order())

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="key", secret="secret", paper=True,
        client_order_id="",
    )
    assert "ord-1" in handler._pending_orders


def test_live_execute_order_calls_submit_order_with_paper_false():
    from trading.impl.live_execution_handler.alpaca_execution_handler import AlpacaExecutionHandler

    collected = []
    handler = AlpacaExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.live_execution_handler.alpaca_paper_execution_handler.submit_order", return_value="ord-2") as mock_sub:
        handler.execute_order(_order(direction="SELL"))

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="SELL", quantity=10,
        api_key="key", secret="secret", paper=False,
        client_order_id="",
    )
```

Also update `test_fill_stream_yields_fill_events_from_websocket`: change the `_pending_orders` seed from a 3-tuple to a 4-tuple:

```python
    handler._pending_orders["ord-1"] = ("AAPL", "BUY", 10, "")
```

And update `test_execute_order_cancels_existing_open_order_for_same_symbol`, `test_execute_order_does_not_cancel_order_for_different_symbol`, `test_execute_order_stale_order_removed_when_cancel_swallows_broker_error`, and `test_poll_fallback_clears_terminal_orders` to use 4-tuples:

```python
    handler._pending_orders["ord-old"] = ("AAPL", "BUY", 100, "")
    handler._pending_orders["ord-msft"] = ("MSFT", "BUY", 50, "")
    handler._pending_orders["ord-99"] = ("AAPL", "BUY", 5, "")
```

- [ ] **Step 3: Run tests to confirm the new tests fail and existing ones still reflect current state**

```
pytest tests/test_alpaca_execution_handlers.py -v
```

Expected: new tests FAIL, updated existing tests FAIL (tuple unpacking error)

- [ ] **Step 4: Add `client_order_id` to `submit_order` in `external/alpaca.py`**

```python
def submit_order(
    symbol: str,
    direction: Literal["BUY", "SELL"],
    quantity: int,
    api_key: str,
    secret: str,
    paper: bool,
    client_order_id: str = "",
) -> str:
    """Submit a market order. Returns the broker order ID."""
    client = TradingClient(api_key, secret, paper=paper)
    side = OrderSide.BUY if direction == "BUY" else OrderSide.SELL
    req = MarketOrderRequest(
        symbol=symbol,
        qty=quantity,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    if client_order_id:
        req.client_order_id = client_order_id
    order = client.submit_order(req)
    return str(order.id)
```

- [ ] **Step 5: Update `AlpacaPaperExecutionHandler`**

In `trading/impl/live_execution_handler/alpaca_paper_execution_handler.py`, change `_pending_orders` type comment and update three places:

1. Change the type hint comment in `__init__`:
```python
        # broker_order_id → (symbol, direction, quantity, client_order_id)
        self._pending_orders: dict[str, tuple[str, str, int, str]] = {}
```

2. Update `execute_order` to pass `client_order_id` and store it in the tuple:
```python
    def execute_order(self, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            self._emit(FillEvent(
                symbol=event.symbol, timestamp=event.timestamp,
                direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
            ))
            return

        for order_id, (symbol, _direction, _qty, _coid) in list(self._pending_orders.items()):
            if symbol != event.symbol:
                continue
            try:
                cancel_order(order_id, self._api_key, self._secret, self._PAPER)
            except Exception as exc:
                logger.warning("Failed cancelling stale order %s for %s: %s", order_id, symbol, exc)
            finally:
                self._pending_orders.pop(order_id, None)

        order_id = submit_order(
            symbol=event.symbol,
            direction=event.direction,
            quantity=event.quantity,
            api_key=self._api_key,
            secret=self._secret,
            paper=self._PAPER,
            client_order_id=event.order_id,
        )
        self._pending_orders[order_id] = (event.symbol, event.direction, event.quantity, event.order_id)
```

3. Update `_bridge_ws` in `fill_stream` to unpack 4-tuple:
```python
        async def _bridge_ws(ws_q: asyncio.Queue):
            while True:
                data = await ws_q.get()
                fill = self._translate(data)
                if fill and fill.symbol and fill.symbol in {s for s, _, _, _ in self._pending_orders.values()}:
                    self._filled_order_ids.add(str(data.order.id))
                    self._pending_orders.pop(str(data.order.id), None)
                    await fill_q.put(fill)
```

4. Update `_poll_fallback` to unpack 4-tuple and set `order_id` on fill:
```python
        async def _poll_fallback():
            while True:
                await asyncio.sleep(_POLL_INTERVAL)
                for order_id, (symbol, direction, qty, client_order_id) in list(self._pending_orders.items()):
                    if order_id in self._filled_order_ids:
                        continue
                    status = get_order_status(order_id, self._api_key, self._secret, self._PAPER)
                    if not status:
                        continue
                    order_status = status["status"]
                    if order_status == "filled":
                        fill = FillEvent(
                            symbol=symbol,
                            timestamp=datetime.now(timezone.utc),
                            direction=direction,
                            quantity=status["filled_qty"],
                            fill_price=status["filled_avg_price"],
                            commission=0.0,
                            order_id=client_order_id,
                        )
                        self._filled_order_ids.add(order_id)
                        self._pending_orders.pop(order_id, None)
                        await fill_q.put(fill)
                    elif order_status in TERMINAL_ORDER_STATUSES:
                        logger.warning(
                            "Order %s for %s %s×%s cleared with status %s",
                            order_id, symbol, direction, qty, order_status,
                        )
                        self._pending_orders.pop(order_id, None)
```

5. Update `_translate` to echo `client_order_id`:
```python
    def _translate(self, data) -> FillEvent | None:
        try:
            order     = data.order
            direction = "BUY" if str(order.side) == "buy" else "SELL"
            return FillEvent(
                symbol     = order.symbol,
                timestamp  = datetime.now(timezone.utc),
                direction  = direction,
                quantity   = int(float(order.filled_qty or 0)),
                fill_price = float(order.filled_avg_price or 0.0),
                commission = 0.0,
                order_id   = str(order.client_order_id or ""),
            )
        except Exception as exc:
            logger.warning("Failed to translate fill: %s", exc)
            return None
```

- [ ] **Step 6: Run all tests to confirm they pass**

```
pytest tests/test_alpaca_execution_handlers.py -v
```

Expected: all PASS

- [ ] **Step 7: Commit**

```bash
git add external/alpaca.py trading/impl/live_execution_handler/alpaca_paper_execution_handler.py tests/test_alpaca_execution_handlers.py
git commit -m "feat: pass client_order_id through Alpaca execution handler"
```

---

### Task 4: Add `strategy_ids` property to `StrategySignalGenerator` and `StrategyContainer`

**Files:**
- Modify: `trading/base/strategy.py`
- Modify: `trading/impl/strategy_signal_generator/strategy_container.py`
- Test: `tests/test_strategy_container.py`

- [ ] **Step 1: Write the failing test**

Add to `tests/test_strategy_container.py`. The file already defines `_AlwaysLong` and `_NeverSignals` stubs — reuse them here:

```python
def test_strategy_container_strategy_ids_returns_registered_names():
    container = StrategyContainer(lambda e: None, lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], name="my_strat"))

    assert container.strategy_ids == ["my_strat"]


def test_strategy_container_strategy_ids_empty_when_no_strategies_added():
    container = StrategyContainer(lambda e: None, lambda s, n: [])
    assert container.strategy_ids == []


def test_strategy_container_strategy_ids_multiple_strategies():
    container = StrategyContainer(lambda e: None, lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], name="strat_a"))
    container.add(_NeverSignals, StrategyParams(symbols=["MSFT"], name="strat_b"))

    assert container.strategy_ids == ["strat_a", "strat_b"]
```

- [ ] **Step 2: Run test to confirm it fails**

```
pytest tests/test_strategy_container.py::test_strategy_container_strategy_ids_returns_registered_names -v
```

Expected: FAIL with `AttributeError: 'StrategyContainer' object has no attribute 'strategy_ids'`

- [ ] **Step 3: Add abstract property to `StrategySignalGenerator`**

In `trading/base/strategy.py`, add to `StrategySignalGenerator`:

```python
    @property
    @abstractmethod
    def strategy_ids(self) -> list[str]:
        """IDs of all registered strategies."""
        ...
```

- [ ] **Step 4: Expose `strategy_ids` on `StrategyContainer`**

In `trading/impl/strategy_signal_generator/strategy_container.py`, add:

```python
    @property
    def strategy_ids(self) -> list[str]:
        return list(self._ids)
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest tests/test_strategy_container.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add trading/base/strategy.py trading/impl/strategy_signal_generator/strategy_container.py tests/test_strategy_container.py
git commit -m "feat: expose strategy_ids property on StrategyContainer"
```

---

### Task 5: Create `TradeLogger` ABC

**Files:**
- Create: `trading/base/live/trade_logger.py`

- [ ] **Step 1: Check the existing `trading/base/live/` directory**

```
ls trading/base/live/
```

Confirm the directory exists and note what other ABCs it contains (e.g. `execution.py`, `reconciler.py`).

- [ ] **Step 2: Create the ABC**

Create `trading/base/live/trade_logger.py`:

```python
from abc import ABC, abstractmethod

from ...events import FillEvent, OrderEvent, StrategyBundleEvent


class TradeLogger(ABC):
    """Persist every signal, order, and fill event for audit and post-trade analysis."""

    @abstractmethod
    def open_session(self, session_id: str, mode: str, strategy_names: list[str]) -> None:
        """Record the start of a new trading session."""
        ...

    @abstractmethod
    def log_signal(self, session_id: str, event: StrategyBundleEvent) -> None:
        """Log a strategy signal bundle (one row per strategy×symbol)."""
        ...

    @abstractmethod
    def log_order(self, session_id: str, event: OrderEvent) -> None:
        """Log an order intent. HOLD orders must be silently ignored."""
        ...

    @abstractmethod
    def log_fill(self, session_id: str, event: FillEvent) -> None:
        """Log an execution fill. HOLD fills must be silently ignored."""
        ...

    @abstractmethod
    def close_session(self, session_id: str) -> None:
        """Record the end of a trading session."""
        ...
```

- [ ] **Step 3: Verify import works**

```
python -c "from trading.base.live.trade_logger import TradeLogger; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add trading/base/live/trade_logger.py
git commit -m "feat: add TradeLogger ABC"
```

---

### Task 6: Create `SqliteTradeLogger`

**Files:**
- Create: `trading/impl/trade_logger/__init__.py`
- Create: `trading/impl/trade_logger/sqlite_trade_logger.py`
- Test: `tests/test_trade_logger.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_trade_logger.py`:

```python
import json
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import pytest

from trading.events import FillEvent, OrderEvent, SignalEvent, StrategyBundleEvent


def _make_logger(tmp_path):
    from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger
    return SqliteTradeLogger(db_path=str(tmp_path / "trades.db"))


def _strategy_bundle(ts=None):
    ts = ts or datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=0.8)},
        per_strategy={"strat_a": {"AAPL": 0.8}, "strat_b": {"AAPL": 0.2}},
    )


def _order(order_id="oid-1"):
    return OrderEvent(
        symbol="AAPL", timestamp=datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc),
        order_type="MARKET", direction="BUY", quantity=10,
        reference_price=150.0, order_id=order_id,
    )


def _fill(order_id="oid-1"):
    return FillEvent(
        symbol="AAPL", timestamp=datetime(2026, 4, 15, 14, 31, tzinfo=timezone.utc),
        direction="BUY", quantity=10, fill_price=150.5, commission=0.0,
        order_id=order_id,
    )


def test_open_session_creates_sessions_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", ["strat_a", "strat_b"])

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT session_id, mode, strategy_names, ended_at FROM sessions").fetchone()
    conn.close()

    assert row[0] == "sess-1"
    assert row[1] == "paper"
    assert json.loads(row[2]) == ["strat_a", "strat_b"]
    assert row[3] is None   # ended_at not set yet


def test_close_session_sets_ended_at(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.close_session("sess-1")

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    ended_at = conn.execute("SELECT ended_at FROM sessions WHERE session_id = 'sess-1'").fetchone()[0]
    conn.close()

    assert ended_at is not None


def test_log_signal_inserts_one_row_per_strategy_symbol(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_signal("sess-1", _strategy_bundle())

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    rows = conn.execute("SELECT strategy_id, symbol, weight FROM signals ORDER BY strategy_id").fetchall()
    conn.close()

    assert len(rows) == 2
    assert rows[0] == ("strat_a", "AAPL", pytest.approx(0.8))
    assert rows[1] == ("strat_b", "AAPL", pytest.approx(0.2))


def test_log_order_inserts_orders_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_order("sess-1", _order("oid-1"))

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT order_id, symbol, direction, quantity, reference_price FROM orders").fetchone()
    conn.close()

    assert row == ("oid-1", "AAPL", "BUY", 10, pytest.approx(150.0))


def test_log_order_skips_hold(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    hold = OrderEvent(
        symbol="", timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
        order_type="MARKET", direction="HOLD", quantity=0,
    )
    logger.log_order("sess-1", hold)

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0]
    conn.close()

    assert count == 0


def test_log_fill_inserts_fills_row(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.log_order("sess-1", _order("oid-1"))
    logger.log_fill("sess-1", _fill("oid-1"))

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    row = conn.execute("SELECT order_id, symbol, direction, quantity, fill_price, commission FROM fills").fetchone()
    conn.close()

    assert row == ("oid-1", "AAPL", "BUY", 10, pytest.approx(150.5), pytest.approx(0.0))


def test_log_fill_skips_hold(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    hold_fill = FillEvent(
        symbol="", timestamp=datetime(2026, 4, 15, tzinfo=timezone.utc),
        direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
    )
    logger.log_fill("sess-1", hold_fill)

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0]
    conn.close()

    assert count == 0


def test_db_file_created_in_nested_directory(tmp_path):
    from trading.impl.trade_logger.sqlite_trade_logger import SqliteTradeLogger
    db_path = str(tmp_path / "nested" / "dir" / "trades.db")
    logger = SqliteTradeLogger(db_path=db_path)
    assert Path(db_path).exists()


def test_multiple_sessions_append_to_same_db(tmp_path):
    logger = _make_logger(tmp_path)
    logger.open_session("sess-1", "paper", [])
    logger.open_session("sess-2", "live", [])

    conn = sqlite3.connect(str(tmp_path / "trades.db"))
    count = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
    conn.close()

    assert count == 2
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_trade_logger.py -v
```

Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Create the `__init__.py`**

Create `trading/impl/trade_logger/__init__.py`:

```python
from .sqlite_trade_logger import SqliteTradeLogger

__all__ = ["SqliteTradeLogger"]
```

- [ ] **Step 4: Create `SqliteTradeLogger`**

Create `trading/impl/trade_logger/sqlite_trade_logger.py`:

```python
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from ...base.live.trade_logger import TradeLogger
from ...events import FillEvent, OrderEvent, StrategyBundleEvent

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id     TEXT PRIMARY KEY,
    started_at     TEXT NOT NULL,
    ended_at       TEXT,
    mode           TEXT NOT NULL,
    strategy_names TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS signals (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    strategy_id  TEXT    NOT NULL,
    symbol       TEXT    NOT NULL,
    weight       REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS orders (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id      TEXT    NOT NULL,
    order_id        TEXT    NOT NULL UNIQUE,
    timestamp       TEXT    NOT NULL,
    symbol          TEXT    NOT NULL,
    direction       TEXT    NOT NULL,
    quantity        INTEGER NOT NULL,
    reference_price REAL    NOT NULL
);
CREATE TABLE IF NOT EXISTS fills (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id   TEXT    NOT NULL,
    order_id     TEXT    NOT NULL,
    timestamp    TEXT    NOT NULL,
    symbol       TEXT    NOT NULL,
    direction    TEXT    NOT NULL,
    quantity     INTEGER NOT NULL,
    fill_price   REAL    NOT NULL,
    commission   REAL    NOT NULL
);
"""


class SqliteTradeLogger(TradeLogger):
    """Appends all trade events to a single SQLite database file."""

    def __init__(self, db_path: str = "logs/trades.db"):
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.executescript(_DDL)
        self._conn.commit()

    def open_session(self, session_id: str, mode: str, strategy_names: list[str]) -> None:
        self._conn.execute(
            "INSERT INTO sessions (session_id, started_at, mode, strategy_names) VALUES (?, ?, ?, ?)",
            (session_id, datetime.now(timezone.utc).isoformat(), mode, json.dumps(strategy_names)),
        )
        self._conn.commit()

    def log_signal(self, session_id: str, event: StrategyBundleEvent) -> None:
        rows = [
            (session_id, event.timestamp.isoformat(), strategy_id, symbol, weight)
            for strategy_id, symbols in event.per_strategy.items()
            for symbol, weight in symbols.items()
        ]
        self._conn.executemany(
            "INSERT INTO signals (session_id, timestamp, strategy_id, symbol, weight) VALUES (?, ?, ?, ?, ?)",
            rows,
        )
        self._conn.commit()

    def log_order(self, session_id: str, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            return
        self._conn.execute(
            "INSERT INTO orders (session_id, order_id, timestamp, symbol, direction, quantity, reference_price)"
            " VALUES (?, ?, ?, ?, ?, ?, ?)",
            (session_id, event.order_id, event.timestamp.isoformat(),
             event.symbol, event.direction, event.quantity, event.reference_price),
        )
        self._conn.commit()

    def log_fill(self, session_id: str, event: FillEvent) -> None:
        if event.direction == "HOLD":
            return
        self._conn.execute(
            "INSERT INTO fills (session_id, order_id, timestamp, symbol, direction, quantity, fill_price, commission)"
            " VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (session_id, event.order_id, event.timestamp.isoformat(),
             event.symbol, event.direction, event.quantity, event.fill_price, event.commission),
        )
        self._conn.commit()

    def close_session(self, session_id: str) -> None:
        self._conn.execute(
            "UPDATE sessions SET ended_at = ? WHERE session_id = ?",
            (datetime.now(timezone.utc).isoformat(), session_id),
        )
        self._conn.commit()
```

- [ ] **Step 5: Run tests to confirm they pass**

```
pytest tests/test_trade_logger.py -v
```

Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add trading/base/live/trade_logger.py trading/impl/trade_logger/__init__.py trading/impl/trade_logger/sqlite_trade_logger.py tests/test_trade_logger.py
git commit -m "feat: implement SqliteTradeLogger"
```

---

### Task 7: Wire `TradeLogger` into `LiveRunner`

**Files:**
- Modify: `trading/live_runner.py`
- Test: `tests/test_live_runner.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_live_runner.py`:

```python
@pytest.mark.asyncio
async def test_trade_logger_open_and_close_session_called():
    from trading.live_runner import LiveRunner
    from unittest.mock import MagicMock

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    strategy = MagicMock()
    strategy.strategy_ids = ["strat_a"]
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()
    trade_logger = MagicMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler,
                        trade_logger=trade_logger, mode="paper")
    await runner.run()

    trade_logger.open_session.assert_called_once()
    session_id, mode, strategy_names = trade_logger.open_session.call_args[0]
    assert mode == "paper"
    assert strategy_names == ["strat_a"]
    # session_id must be a non-empty string (UUID)
    assert isinstance(session_id, str) and len(session_id) > 0

    trade_logger.close_session.assert_called_once_with(session_id)


@pytest.mark.asyncio
async def test_trade_logger_logs_strategy_bundle():
    from trading.live_runner import LiveRunner
    from trading.events import SignalEvent

    ts = datetime(2024, 1, 2, 16, 5)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=0.8)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": sig},
        per_strategy={"strat_a": {"AAPL": 1.0}},
    )

    events = queue.Queue()
    events.put(bundle)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1
    data.update_bars_async = _update

    strategy = MagicMock()
    strategy.strategy_ids = []
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()
    trade_logger = MagicMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler,
                        trade_logger=trade_logger, mode="paper")
    await runner.run()

    trade_logger.log_signal.assert_called_once()
    assert trade_logger.log_signal.call_args[0][1] is bundle


@pytest.mark.asyncio
async def test_trade_logger_logs_order_but_not_hold():
    from trading.live_runner import LiveRunner

    ts = datetime(2024, 1, 2, 16, 5)
    buy_order = OrderEvent(symbol="AAPL", timestamp=ts, order_type="MARKET",
                           direction="BUY", quantity=5, order_id="oid-1")
    hold_order = OrderEvent(symbol="", timestamp=ts, order_type="MARKET",
                            direction="HOLD", quantity=0)

    events = queue.Queue()
    events.put(buy_order)
    events.put(hold_order)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1
    data.update_bars_async = _update

    strategy = MagicMock()
    strategy.strategy_ids = []
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()
    trade_logger = MagicMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler,
                        trade_logger=trade_logger, mode="paper")
    await runner.run()

    trade_logger.log_order.assert_called_once()
    assert trade_logger.log_order.call_args[0][1] is buy_order


@pytest.mark.asyncio
async def test_trade_logger_is_optional():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    # No trade_logger — must not raise
    runner = LiveRunner(events, data, MagicMock(), portfolio, execution, reconciler)
    await runner.run()
```

- [ ] **Step 2: Run tests to confirm they fail**

```
pytest tests/test_live_runner.py::test_trade_logger_open_and_close_session_called tests/test_live_runner.py::test_trade_logger_logs_strategy_bundle tests/test_live_runner.py::test_trade_logger_logs_order_but_not_hold tests/test_live_runner.py::test_trade_logger_is_optional -v
```

Expected: FAIL with `TypeError` (unexpected keyword arguments)

- [ ] **Step 3: Update `LiveRunner`**

Replace `trading/live_runner.py` with:

```python
import asyncio
import logging
import queue
import signal
import uuid

from .base.live.execution  import LiveExecutionHandler
from .base.live.reconciler import PositionReconciler
from .base.live.risk_guard import RiskGuard
from .base.live.trade_logger import TradeLogger
from .base.live.runner     import LiveRunner as LiveRunnerBase
from .base.portfolio       import Portfolio
from .base.strategy        import StrategySignalGenerator
from .base.data            import DataHandler
from .events               import EventType

logger = logging.getLogger(__name__)


class LiveRunner(LiveRunnerBase):
    """
    Asyncio event loop for live/paper trading.

    Lifecycle:
      1. reconciler.hydrate(portfolio) — load broker positions
      2. Open fill stream (WebSocket + polling fallback)
      3. Drain fill stream as background task
      4. Loop: await next bar → drain event queue → dispatch
      5. Shutdown on SIGTERM / KeyboardInterrupt

    Event dispatch is identical to Backtester.run().
    """

    def __init__(
        self,
        events:       queue.Queue,
        data:         DataHandler,
        strategy:     StrategySignalGenerator,
        portfolio:    Portfolio,
        execution:    LiveExecutionHandler,
        reconciler:   PositionReconciler,
        risk_guard:   RiskGuard | None = None,
        trade_logger: TradeLogger | None = None,
        mode:         str = "paper",
    ):
        self._events       = events
        self._data         = data
        self._strategy     = strategy
        self._portfolio    = portfolio
        self._execution    = execution
        self._reconciler   = reconciler
        self._risk_guard   = risk_guard
        self._trade_logger = trade_logger
        self._mode         = mode
        self._shutdown     = False
        self._session_id   = ""

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            try:
                loop.add_signal_handler(sig, self._request_shutdown)
            except (OSError, NotImplementedError):
                pass

        await self._reconciler.hydrate(self._portfolio)
        self._data.prefill()
        if self._risk_guard is not None:
            self._risk_guard.reset_day(self._portfolio.equity)

        self._session_id = str(uuid.uuid4())
        if self._trade_logger is not None:
            self._trade_logger.open_session(
                self._session_id, self._mode, self._strategy.strategy_ids
            )

        async with self._execution.fill_stream() as fill_q:
            drain_task = asyncio.create_task(self._drain_fill_stream(fill_q))
            try:
                while not self._shutdown:
                    bar_ready = await self._data.update_bars_async()
                    if not bar_ready:
                        break
                    while not self._events.empty():
                        try:
                            event = self._events.get_nowait()
                        except queue.Empty:
                            break
                        self._dispatch(event)
            finally:
                drain_task.cancel()
                try:
                    await drain_task
                except asyncio.CancelledError:
                    pass
                if self._trade_logger is not None:
                    self._trade_logger.close_session(self._session_id)

    def _request_shutdown(self) -> None:
        logger.info("Shutdown requested.")
        self._shutdown = True
        if hasattr(self._data, "request_shutdown"):
            self._data.request_shutdown()

    async def _drain_fill_stream(self, fill_q: asyncio.Queue) -> None:
        while True:
            try:
                fill_event = await asyncio.wait_for(fill_q.get(), timeout=0.5)
                self._events.put(fill_event)
            except asyncio.TimeoutError:
                continue

    def _dispatch(self, event) -> None:
        match event.type:
            case EventType.BAR_BUNDLE:
                self._portfolio.fill_pending_orders(event)
                self._strategy.get_signals(event)
            case EventType.STRATEGY_BUNDLE:
                if self._trade_logger is not None:
                    self._trade_logger.log_signal(self._session_id, event)
                self._portfolio.on_signal(event)
            case EventType.ORDER:
                if self._trade_logger is not None and event.direction != "HOLD":
                    self._trade_logger.log_order(self._session_id, event)
                self._execution.execute_order(event)
            case EventType.FILL:
                if self._trade_logger is not None and event.direction != "HOLD":
                    self._trade_logger.log_fill(self._session_id, event)
                self._portfolio.on_fill(event)
```

- [ ] **Step 4: Run all live runner tests**

```
pytest tests/test_live_runner.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/live_runner.py tests/test_live_runner.py
git commit -m "feat: wire TradeLogger into LiveRunner"
```

---

### Task 8: Wire `SqliteTradeLogger` in `run_live.py`

**Files:**
- Modify: `run_live.py`

- [ ] **Step 1: Add import and construct logger**

In `run_live.py`, add to the imports block:

```python
from trading.impl.trade_logger import SqliteTradeLogger
```

After the `risk_guard = RiskGuard(...)` block, add:

```python
trade_logger = SqliteTradeLogger(db_path="logs/trades.db")
```

- [ ] **Step 2: Pass to `LiveRunner`**

Change the `runner = LiveRunner(...)` call:

```python
runner = LiveRunner(
    events, data, strategy, portfolio, execution, reconciler, risk_guard,
    trade_logger=trade_logger,
    mode=MODE,
)
```

- [ ] **Step 3: Run the full test suite to confirm nothing is broken**

```
pytest tests/ -v --ignore=tests/test_index_constituents_external.py --ignore=tests/test_alpaca_external.py --ignore=tests/test_yahoo_external.py
```

Expected: all PASS

- [ ] **Step 4: Commit**

```bash
git add run_live.py
git commit -m "feat: wire SqliteTradeLogger into run_live.py"
```
