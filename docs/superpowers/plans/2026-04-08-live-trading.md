# Live Trading Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extend the backtesting engine to support live and paper trading via Alpaca, using an asyncio event loop with WebSocket fill streaming and broker-side position reconciliation.

**Architecture:** A new `LiveRunner` replaces `Backtester` for live use; `AlpacaDataHandler` blocks in `update_bars_async()` until the next bar boundary; `AlpacaPaperExecutionHandler` / `AlpacaExecutionHandler` route orders to Alpaca and return fills via WebSocket with a polling fallback. `RiskGuard` is injected into `SimplePortfolio` to check daily loss limits and per-symbol caps before signals are processed. All Alpaca SDK calls are isolated in `external/alpaca.py`.

**Tech Stack:** Python 3.10+, `alpaca-py`, `pytest`, `pytest-asyncio`, `unittest.mock`

---

## File Map

### New files
| File | Purpose |
|---|---|
| `external/alpaca.py` | Thin wrappers over `alpaca-py` SDK — pure functions, no state |
| `trading/base/live/__init__.py` | Package init |
| `trading/base/live/runner.py` | `LiveRunner` ABC |
| `trading/base/live/risk_guard.py` | `RiskGuard` ABC |
| `trading/base/live/reconciler.py` | `PositionReconciler` ABC |
| `trading/base/live/execution.py` | `LiveExecutionHandler` ABC (adds `fill_stream()`) |
| `trading/impl/risk_guard.py` | Concrete `RiskGuard` — daily loss + per-symbol cap |
| `trading/impl/alpaca_data_handler.py` | `AlpacaDataHandler` — async bar fetching |
| `trading/impl/alpaca_paper_execution_handler.py` | Routes orders to Alpaca paper API |
| `trading/impl/alpaca_execution_handler.py` | Routes orders to Alpaca live API + fill stream |
| `trading/impl/alpaca_reconciler.py` | Hydrates portfolio from Alpaca `/positions` + `/account` |
| `trading/impl/live_runner.py` | Concrete `LiveRunner` — asyncio loop |
| `run_live.py` | Wiring point (mirrors `run_backtest.py`) |
| `tests/test_risk_guard.py` | RiskGuard unit tests |
| `tests/test_alpaca_external.py` | `external/alpaca.py` unit tests |
| `tests/test_alpaca_data_handler.py` | AlpacaDataHandler tests |
| `tests/test_alpaca_execution_handlers.py` | Execution handler tests |
| `tests/test_alpaca_reconciler.py` | Reconciler tests |
| `tests/test_live_runner.py` | LiveRunner tests |
| `tests/test_portfolio_restore.py` | SimplePortfolio restore + risk_guard tests |

### Modified files
| File | Change |
|---|---|
| `trading/base/data.py` | Add `update_bars_async()` default |
| `trading/base/execution.py` | Add `execute_order_async()` default |
| `trading/base/portfolio.py` | Add abstract `restore()` |
| `trading/base/__init__.py` | Export new live ABCs |
| `trading/impl/simple_portfolio.py` | Add `restore()` + optional `risk_guard` param |
| `trading/impl/__init__.py` | Export new impl classes |
| `requirements.txt` | Add `alpaca-py`, `pytest-asyncio` |

---

## Task 1: Base ABC extensions + `trading/base/live/` package

**Files:**
- Modify: `trading/base/data.py`
- Modify: `trading/base/execution.py`
- Modify: `trading/base/portfolio.py`
- Modify: `trading/base/__init__.py`
- Create: `trading/base/live/__init__.py`
- Create: `trading/base/live/runner.py`
- Create: `trading/base/live/risk_guard.py`
- Create: `trading/base/live/reconciler.py`
- Create: `trading/base/live/execution.py`
- Test: `tests/test_data.py` (extend existing)

- [ ] **Step 1: Write failing tests for async defaults**

Add to `tests/test_data.py`:

```python
import asyncio
from unittest.mock import MagicMock, patch

def test_update_bars_async_default_calls_update_bars():
    """Default update_bars_async() wraps update_bars() in a thread."""
    from trading.impl.multi_csv_data_handler import MultiCSVDataHandler

    handler = MultiCSVDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-10",
    )
    with patch.object(handler, "update_bars", return_value=False) as mock_sync:
        result = asyncio.run(handler.update_bars_async())
    assert result is False
    mock_sync.assert_called_once()
```

Run: `pytest tests/test_data.py::test_update_bars_async_default_calls_update_bars -v`
Expected: **FAIL** — `AttributeError: 'MultiCSVDataHandler' object has no attribute 'update_bars_async'`

- [ ] **Step 2: Add `update_bars_async()` to `DataHandler`**

Edit `trading/base/data.py`:

```python
import asyncio
from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, TickEvent


class DataHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def update_bars(self) -> bool:
        """Emit the next bar bundle as a BarBundleEvent. Returns False when data is exhausted."""
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        """Return the last N bars for a symbol."""
        ...

    async def update_bars_async(self) -> bool:
        """Default: wraps update_bars() via asyncio.to_thread. Override for real async."""
        return await asyncio.to_thread(self.update_bars)
```

- [ ] **Step 3: Add `execute_order_async()` to `ExecutionHandler`**

Edit `trading/base/execution.py`:

```python
import asyncio
from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, OrderEvent


class ExecutionHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def execute_order(self, event: OrderEvent) -> None:
        """Simulate or route the order and emit a FillEvent."""
        ...

    async def execute_order_async(self, event: OrderEvent) -> None:
        """Default: wraps execute_order() via asyncio.to_thread. Override for real async."""
        await asyncio.to_thread(self.execute_order, event)
```

- [ ] **Step 4: Add abstract `restore()` to `Portfolio`**

Edit `trading/base/portfolio.py`:

```python
from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, Event, FillEvent, StrategyBundleEvent


class Portfolio(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None: ...

    @abstractmethod
    def on_signal(self, event: StrategyBundleEvent) -> None: ...

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None: ...

    @abstractmethod
    def restore(self, holdings: dict[str, int], cash: float) -> None:
        """Hydrate portfolio state from an external source (e.g. broker reconciliation)."""
        ...

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...

    @property
    @abstractmethod
    def strategy_pnl(self) -> list[dict]: ...

    @property
    @abstractmethod
    def strategy_traded_value(self) -> dict[str, float]: ...
```

- [ ] **Step 5: Create `trading/base/live/` package with four ABCs**

Create `trading/base/live/__init__.py`:
```python
from .execution  import LiveExecutionHandler
from .reconciler import PositionReconciler
from .risk_guard import RiskGuard
from .runner     import LiveRunner

__all__ = ["LiveExecutionHandler", "LiveRunner", "PositionReconciler", "RiskGuard"]
```

Create `trading/base/live/runner.py`:
```python
from abc import ABC, abstractmethod


class LiveRunner(ABC):
    @abstractmethod
    async def run(self) -> None:
        """Start the live trading loop. Runs until shutdown."""
        ...
```

Create `trading/base/live/risk_guard.py`:
```python
from abc import ABC, abstractmethod

from ...events import StrategyBundleEvent


class RiskGuard(ABC):
    @abstractmethod
    def check(
        self,
        event: StrategyBundleEvent,
        current_prices: dict[str, float],
        current_equity: float,
    ) -> StrategyBundleEvent | None:
        """Return event (possibly modified) or None to halt trading."""
        ...

    @abstractmethod
    def reset_day(self, current_equity: float) -> None:
        """Snapshot day-open equity. Call at start of each session."""
        ...
```

Create `trading/base/live/reconciler.py`:
```python
from abc import ABC, abstractmethod

from ...base.portfolio import Portfolio


class PositionReconciler(ABC):
    @abstractmethod
    async def hydrate(self, portfolio: Portfolio) -> None:
        """Query broker state and call portfolio.restore(holdings, cash)."""
        ...
```

Create `trading/base/live/execution.py`:
```python
from abc import abstractmethod
from contextlib import asynccontextmanager
from typing import AsyncIterator
import asyncio

from ...base.execution import ExecutionHandler
from ...events import FillEvent


class LiveExecutionHandler(ExecutionHandler):
    @abstractmethod
    @asynccontextmanager
    async def fill_stream(self) -> AsyncIterator[asyncio.Queue]:
        """Async context manager yielding asyncio.Queue[FillEvent].
        Handles WebSocket connection and polling fallback internally."""
        ...
```

- [ ] **Step 6: Export from `trading/base/__init__.py`**

Edit `trading/base/__init__.py`:

```python
from .data          import DataHandler
from .execution     import ExecutionHandler
from .live          import LiveExecutionHandler, LiveRunner, PositionReconciler, RiskGuard
from .portfolio     import Portfolio
from .result_writer import BacktestResultWriter
from .strategy      import Strategy, StrategyBase, StrategySignalGenerator
from .strategy_params import StrategyParams
from .strategy_params_loader import StrategyParamsLoader
from .universe_builder import UniverseBuilder

__all__ = [
    "BacktestResultWriter",
    "DataHandler",
    "ExecutionHandler",
    "LiveExecutionHandler",
    "LiveRunner",
    "Portfolio",
    "PositionReconciler",
    "RiskGuard",
    "Strategy",
    "StrategyBase",
    "StrategySignalGenerator",
    "StrategyParams",
    "StrategyParamsLoader",
    "UniverseBuilder",
]
```

- [ ] **Step 7: Run tests to verify passing**

Run: `pytest tests/test_data.py::test_update_bars_async_default_calls_update_bars -v`
Expected: **PASS**

Run: `pytest tests/ -v --ignore=tests/test_yahoo_external.py --ignore=tests/test_index_constituents_external.py`
Expected: all existing tests still **PASS** (no regressions)

- [ ] **Step 8: Commit**

```bash
git add trading/base/data.py trading/base/execution.py trading/base/portfolio.py \
        trading/base/__init__.py trading/base/live/ tests/test_data.py
git commit -m "feat: extend base ABCs with async defaults and live/ package"
```

---

## Task 2: `external/alpaca.py` — Alpaca SDK wrappers

**Files:**
- Create: `external/alpaca.py`
- Modify: `requirements.txt`
- Test: `tests/test_alpaca_external.py`

- [ ] **Step 1: Add dependencies to `requirements.txt`**

Edit `requirements.txt` — append:
```
# Live trading:
alpaca-py>=0.13
pytest-asyncio>=0.23
```

Install: `pip install alpaca-py pytest-asyncio`

- [ ] **Step 2: Write failing tests**

Create `tests/test_alpaca_external.py`:

```python
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
```

Run: `pytest tests/test_alpaca_external.py -v`
Expected: **FAIL** — `ModuleNotFoundError: No module named 'external.alpaca'`

- [ ] **Step 3: Implement `external/alpaca.py`**

Create `external/alpaca.py`:

```python
"""
Thin wrappers over alpaca-py SDK.
Pure functions, no state, no imports from trading/.
"""
import asyncio
import contextlib
from datetime import datetime
from typing import Literal

from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.stream import TradingStream


def _timeframe(bar_freq: str) -> TimeFrame:
    if bar_freq == "1d":
        return TimeFrame.Day
    if bar_freq == "1h":
        return TimeFrame.Hour
    if bar_freq == "1m":
        return TimeFrame.Minute
    if bar_freq.endswith("m"):
        minutes = int(bar_freq[:-1])
        return TimeFrame(minutes, TimeFrameUnit.Minute)
    raise ValueError(f"Unsupported bar_freq: {bar_freq!r}")


def fetch_bars(
    symbols: list[str],
    bar_freq: str,
    start: datetime,
    end: datetime,
    api_key: str,
    secret: str,
) -> dict[str, dict]:
    """Fetch OHLCV bars for symbols. Returns {symbol: {open, high, low, close, volume, timestamp}}."""
    client = StockHistoricalDataClient(api_key, secret)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=_timeframe(bar_freq),
        start=start,
        end=end,
    )
    bar_set = client.get_stock_bars(request)
    result = {}
    for symbol in symbols:
        bars = bar_set[symbol]
        if not bars:
            continue
        bar = bars[-1]
        result[symbol] = {
            "timestamp": bar.timestamp,
            "open":      float(bar.open),
            "high":      float(bar.high),
            "low":       float(bar.low),
            "close":     float(bar.close),
            "volume":    float(bar.volume),
        }
    return result


def submit_order(
    symbol: str,
    direction: Literal["BUY", "SELL"],
    quantity: int,
    api_key: str,
    secret: str,
    paper: bool,
) -> str:
    """Submit a market order. Returns the broker order ID."""
    client = TradingClient(api_key, secret, paper=paper)
    side = OrderSide.BUY if direction == "BUY" else OrderSide.SELL
    order = client.submit_order(
        MarketOrderRequest(
            symbol=symbol,
            qty=quantity,
            side=side,
            time_in_force=TimeInForce.DAY,
        )
    )
    return str(order.id)


def get_positions(api_key: str, secret: str, paper: bool) -> dict[str, int]:
    """Return current positions as {symbol: quantity}."""
    client = TradingClient(api_key, secret, paper=paper)
    positions = client.get_all_positions()
    return {p.symbol: int(float(p.qty)) for p in positions}


def get_account(api_key: str, secret: str, paper: bool) -> float:
    """Return available cash balance."""
    client = TradingClient(api_key, secret, paper=paper)
    account = client.get_account()
    return float(account.cash)


def get_order_status(
    order_id: str,
    api_key: str,
    secret: str,
    paper: bool,
) -> dict | None:
    """Return fill status dict or None on error.
    Keys: status, filled_qty, filled_avg_price, symbol, direction."""
    client = TradingClient(api_key, secret, paper=paper)
    try:
        order = client.get_order_by_id(order_id)
        return {
            "status":            str(order.status),
            "filled_qty":        int(float(order.filled_qty or 0)),
            "filled_avg_price":  float(order.filled_avg_price or 0.0),
            "symbol":            order.symbol,
            "direction":         "BUY" if str(order.side) == "buy" else "SELL",
        }
    except Exception:
        return None


@contextlib.asynccontextmanager
async def open_fill_stream(api_key: str, secret: str, paper: bool):
    """Async context manager that yields asyncio.Queue[dict] of raw trade update dicts.
    The queue receives every fill/partial_fill event from Alpaca's trade update stream."""
    q: asyncio.Queue = asyncio.Queue()
    stream = TradingStream(api_key, secret, paper=paper)

    @stream.subscribe_trade_updates
    async def _handler(data):
        if hasattr(data, "event") and str(data.event) in ("fill", "partial_fill"):
            await q.put(data)

    task = asyncio.create_task(stream.run())
    try:
        yield q
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_alpaca_external.py -v`
Expected: all 5 tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add external/alpaca.py requirements.txt tests/test_alpaca_external.py
git commit -m "feat: add external/alpaca.py SDK wrappers"
```

---

## Task 3: Concrete `RiskGuard`

**Files:**
- Create: `trading/impl/risk_guard.py`
- Test: `tests/test_risk_guard.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_risk_guard.py`:

```python
from datetime import datetime
from trading.events import SignalEvent, StrategyBundleEvent


def _bundle(signals: dict[str, float], ts=None) -> StrategyBundleEvent:
    ts = ts or datetime(2024, 1, 2, 16, 5)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={
            sym: SignalEvent(symbol=sym, timestamp=ts, signal=sig)
            for sym, sig in signals.items()
        },
        per_strategy={"s1": {sym: 1.0 for sym in signals}},
    )


def test_check_passes_event_when_within_limits():
    from trading.impl.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=10_000.0)

    assert result is not None
    assert result.combined["AAPL"].signal == 0.5


def test_check_returns_none_when_daily_loss_limit_breached():
    from trading.impl.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    # equity dropped 6% — exceeds 5% limit
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=9_400.0)

    assert result is None


def test_check_clamps_signal_when_position_cap_exceeded():
    from trading.impl.risk_guard import RiskGuard

    # initial_capital=10_000, max_position_pct=0.10
    # At price=100, signal=0.5 → target_qty = 0.5 * 10000 / 100 = 50 shares = $5000 = 50% of equity
    # max_position = 0.10 * 10000 = $1000 → max_signal = 0.10 * 10000 / 10000 = 0.10
    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.10, initial_capital=10_000.0)
    guard.reset_day(current_equity=10_000.0)

    event = _bundle({"AAPL": 0.5})
    result = guard.check(event, current_prices={"AAPL": 100.0}, current_equity=10_000.0)

    assert result is not None
    assert result.combined["AAPL"].signal == 0.10


def test_check_auto_resets_on_new_trading_day():
    from trading.impl.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=9_000.0)   # day 1 open

    # Day 2 — new timestamp date triggers auto-reset
    event = _bundle({"AAPL": 0.2}, ts=datetime(2024, 1, 3, 16, 5))
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=9_000.0)

    # Should NOT be None — day was reset with 9000 as new baseline
    assert result is not None


def test_reset_day_updates_baseline():
    from trading.impl.risk_guard import RiskGuard

    guard = RiskGuard(max_daily_loss_pct=0.05, max_position_pct=0.20, initial_capital=10_000.0)
    guard.reset_day(current_equity=8_000.0)

    event = _bundle({"AAPL": 0.2})
    # 6% drop from 8000 = 7520 — breaches limit
    result = guard.check(event, current_prices={"AAPL": 150.0}, current_equity=7_520.0)
    assert result is None
```

Run: `pytest tests/test_risk_guard.py -v`
Expected: **FAIL** — `ModuleNotFoundError`

- [ ] **Step 2: Implement `trading/impl/risk_guard.py`**

```python
import logging
from datetime import date

from ..base.live.risk_guard import RiskGuard as RiskGuardBase
from ..events import SignalEvent, StrategyBundleEvent

logger = logging.getLogger(__name__)


class RiskGuard(RiskGuardBase):
    """
    Two checks applied before each signal bundle reaches the portfolio:

    1. Daily loss limit: if equity has fallen more than max_daily_loss_pct from
       the day's opening equity, halt all new signals for the session.

    2. Per-symbol position cap: clamp each signal weight so the resulting
       nominal allocation does not exceed max_position_pct × current_equity.

    reset_day(equity) must be called at each session open.
    The guard also auto-resets when the event timestamp moves to a new calendar date.
    """

    def __init__(
        self,
        max_daily_loss_pct: float,
        max_position_pct: float,
        initial_capital: float,
    ):
        self._max_daily_loss_pct = max_daily_loss_pct
        self._max_position_pct   = max_position_pct
        self._initial_capital    = initial_capital
        self._day_open_equity: float | None = None
        self._last_reset_date: date | None  = None

    def reset_day(self, current_equity: float) -> None:
        self._day_open_equity  = current_equity
        self._last_reset_date  = date.today()

    def check(
        self,
        event: StrategyBundleEvent,
        current_prices: dict[str, float],
        current_equity: float,
    ) -> StrategyBundleEvent | None:
        # Auto-reset on new trading day
        event_date = event.timestamp.date()
        if self._last_reset_date != event_date:
            self.reset_day(current_equity)

        # Daily loss limit
        if (
            self._day_open_equity is not None
            and current_equity < self._day_open_equity * (1 - self._max_daily_loss_pct)
        ):
            logger.warning(
                "RiskGuard: daily loss limit breached. equity=%.2f day_open=%.2f limit=%.1f%%",
                current_equity,
                self._day_open_equity,
                self._max_daily_loss_pct * 100,
            )
            return None

        # Per-symbol position cap
        max_signal = (self._max_position_pct * current_equity) / self._initial_capital
        capped: dict[str, SignalEvent] = {}
        for symbol, sig_event in event.combined.items():
            capped_weight = min(sig_event.signal, max_signal) if sig_event.signal > 0 else sig_event.signal
            capped[symbol] = SignalEvent(
                symbol=symbol,
                timestamp=sig_event.timestamp,
                signal=capped_weight,
            )

        return StrategyBundleEvent(
            timestamp=event.timestamp,
            combined=capped,
            per_strategy=event.per_strategy,
        )
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_risk_guard.py -v`
Expected: all 5 tests **PASS**

- [ ] **Step 4: Commit**

```bash
git add trading/impl/risk_guard.py tests/test_risk_guard.py
git commit -m "feat: add RiskGuard with daily loss limit and per-symbol cap"
```

---

## Task 4: `SimplePortfolio` — `restore()` + `risk_guard` injection

**Files:**
- Modify: `trading/impl/simple_portfolio.py`
- Test: `tests/test_portfolio_restore.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_portfolio_restore.py`:

```python
from datetime import datetime
from unittest.mock import MagicMock

from trading.events import SignalEvent, StrategyBundleEvent, TickEvent


def _get_bars(prices: dict[str, float]):
    def get_bars(symbol, n=1):
        p = prices.get(symbol, 100.0)
        return [TickEvent(symbol=symbol, timestamp=datetime(2024,1,2),
                          open=p, high=p, low=p, close=p, volume=1000.0)]
    return get_bars


def _bundle(symbol: str, signal: float) -> StrategyBundleEvent:
    ts = datetime(2024, 1, 2, 16, 5)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal=signal)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={symbol: sig},
        per_strategy={"s1": {symbol: 1.0}},
    )


def test_restore_sets_holdings_and_cash():
    from trading.impl.simple_portfolio import SimplePortfolio

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
    )
    portfolio.restore(holdings={"AAPL": 10}, cash=8_500.0)

    assert portfolio._holdings["AAPL"] == 10
    assert portfolio._cash == 8_500.0


def test_on_signal_drops_signal_when_risk_guard_returns_none():
    from trading.impl.simple_portfolio import SimplePortfolio

    mock_guard = MagicMock()
    mock_guard.check.return_value = None  # guard halts trading

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
        risk_guard=mock_guard,
    )
    portfolio.on_signal(_bundle("AAPL", 0.5))

    assert portfolio._pending_signals is None


def test_on_signal_uses_modified_event_from_risk_guard():
    from trading.impl.simple_portfolio import SimplePortfolio
    from trading.events import SignalEvent, StrategyBundleEvent

    ts = datetime(2024, 1, 2, 16, 5)
    clamped_sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=0.1)
    clamped_bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": clamped_sig},
        per_strategy={"s1": {"AAPL": 1.0}},
    )
    mock_guard = MagicMock()
    mock_guard.check.return_value = clamped_bundle

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
        risk_guard=mock_guard,
    )
    portfolio.on_signal(_bundle("AAPL", 0.5))

    assert portfolio._pending_signals is not None
    assert portfolio._pending_signals.combined["AAPL"].signal == 0.1


def test_on_signal_without_risk_guard_stores_pending_signals():
    from trading.impl.simple_portfolio import SimplePortfolio

    portfolio = SimplePortfolio(
        emit=MagicMock(),
        get_bars=_get_bars({"AAPL": 150.0}),
        symbols=["AAPL"],
        initial_capital=10_000.0,
    )
    bundle = _bundle("AAPL", 0.5)
    portfolio.on_signal(bundle)

    assert portfolio._pending_signals is bundle
```

Run: `pytest tests/test_portfolio_restore.py -v`
Expected: **FAIL** — `TypeError: SimplePortfolio.__init__() got an unexpected keyword argument 'risk_guard'` (and `restore` missing)

- [ ] **Step 2: Add `restore()` and `risk_guard` to `SimplePortfolio`**

In `trading/impl/simple_portfolio.py`, update `__init__` signature:

```python
def __init__(
    self,
    emit:             Callable[[Event], None],
    get_bars:         Callable[[str, int], list[TickEvent]],
    symbols:          list[str],
    initial_capital:  float = 10_000.0,
    max_leverage:     float = 1.0,
    fill_cost_buffer: float = 0.002,
    risk_guard=None,   # RiskGuard | None — avoid circular import, type checked at runtime
):
```

Add `self._risk_guard = risk_guard` in `__init__` body (after `self._strategy_qty`).

Replace the `on_signal` method:

```python
def on_signal(self, event: StrategyBundleEvent) -> None:
    if self._risk_guard is not None:
        market_value = sum(
            self._holdings.get(s, 0) * bars[-1].close
            for s in self._symbols
            if (bars := self._get_bars(s, 1))
        )
        current_equity = self._cash + market_value
        current_prices = {
            s: bars[-1].close
            for s in self._symbols
            if (bars := self._get_bars(s, 1))
        }
        event = self._risk_guard.check(event, current_prices, current_equity)
        if event is None:
            return
    self._pending_signals = event
```

Add `restore()` method (after `on_signal`):

```python
def restore(self, holdings: dict[str, int], cash: float) -> None:
    self._holdings = dict(holdings)
    self._cash = cash
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_portfolio_restore.py -v`
Expected: all 4 tests **PASS**

Run: `pytest tests/test_portfolio.py -v`
Expected: all existing portfolio tests still **PASS**

- [ ] **Step 4: Commit**

```bash
git add trading/impl/simple_portfolio.py tests/test_portfolio_restore.py
git commit -m "feat: add SimplePortfolio.restore() and optional risk_guard injection"
```

---

## Task 5: `AlpacaDataHandler`

**Files:**
- Create: `trading/impl/alpaca_data_handler.py`
- Test: `tests/test_alpaca_data_handler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_alpaca_data_handler.py`:

```python
import asyncio
from collections import deque
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest


def _raw_bar(symbol="AAPL", o=100.0, h=101.0, l=99.0, c=100.5, v=50000.0):
    return {
        "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
        "open": o, "high": h, "low": l, "close": c, "volume": v,
    }


def test_get_latest_bars_returns_empty_before_any_bars():
    from trading.impl.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    assert handler.get_latest_bars("AAPL", 1) == []


def test_get_latest_bars_returns_tick_events_after_update():
    from trading.impl.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    fake_bars = {"AAPL": _raw_bar()}
    with patch("trading.impl.alpaca_data_handler.fetch_bars", return_value=fake_bars):
        result = asyncio.run(handler.update_bars_async())

    assert result is True
    ticks = handler.get_latest_bars("AAPL", 1)
    assert len(ticks) == 1
    assert ticks[0].close == 100.5
    assert ticks[0].symbol == "AAPL"


def test_update_bars_async_emits_bar_bundle_event():
    from trading.impl.alpaca_data_handler import AlpacaDataHandler
    from trading.events import EventType

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )
    fake_bars = {"AAPL": _raw_bar()}
    with patch("trading.impl.alpaca_data_handler.fetch_bars", return_value=fake_bars):
        asyncio.run(handler.update_bars_async())

    assert len(collected) == 1
    assert collected[0].type == EventType.BAR_BUNDLE
    assert "AAPL" in collected[0].bars


def test_update_bars_async_returns_false_when_shutdown_requested():
    from trading.impl.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    async def _run():
        handler.request_shutdown()
        return await handler.update_bars_async()

    result = asyncio.run(_run())
    assert result is False
```

Run: `pytest tests/test_alpaca_data_handler.py -v`
Expected: **FAIL** — `ModuleNotFoundError`

- [ ] **Step 2: Implement `trading/impl/alpaca_data_handler.py`**

```python
import asyncio
from collections import deque
from datetime import datetime, timedelta, timezone
from typing import Callable
from zoneinfo import ZoneInfo

from ..base.data import DataHandler
from ..events import BarBundleEvent, Event, TickEvent
from external.alpaca import fetch_bars

ET = ZoneInfo("America/New_York")
_DAILY_BAR_HOUR   = 16
_DAILY_BAR_MINUTE = 5


class AlpacaDataHandler(DataHandler):
    """
    Live DataHandler backed by Alpaca's market data API.

    bar_freq: "1d" for daily bars, "Xm" for X-minute intraday bars (e.g. "5m").

    update_bars_async() sleeps until the next bar boundary, fetches the
    completed bar for all symbols, pushes to internal deques, and emits a
    BarBundleEvent. Returns False if request_shutdown() was called.
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        bar_freq:    str,
        api_key:     str,
        secret:      str,
        max_history: int = 200,
    ):
        super().__init__(emit)
        self._symbols        = symbols
        self._bar_freq       = bar_freq
        self._api_key        = api_key
        self._secret         = secret
        self._max_history    = max_history
        self._deques: dict[str, deque] = {s: deque(maxlen=max_history) for s in symbols}
        self._shutdown_event = asyncio.Event()

    def request_shutdown(self) -> None:
        self._shutdown_event.set()

    def update_bars(self) -> bool:
        """Synchronous fallback — not used in live; runs asyncio internally."""
        return asyncio.run(self.update_bars_async())

    async def update_bars_async(self) -> bool:
        if self._shutdown_event.is_set():
            return False

        sleep_secs = self._seconds_until_next_bar()
        if sleep_secs > 0:
            sleep_task    = asyncio.create_task(asyncio.sleep(sleep_secs))
            shutdown_task = asyncio.create_task(self._shutdown_event.wait())
            done, pending = await asyncio.wait(
                [sleep_task, shutdown_task],
                return_when=asyncio.FIRST_COMPLETED,
            )
            for t in pending:
                t.cancel()
            if self._shutdown_event.is_set():
                return False

        now = datetime.now(tz=ET)
        bars = fetch_bars(
            symbols  = self._symbols,
            bar_freq = self._bar_freq,
            start    = now - timedelta(days=3 if self._bar_freq == "1d" else 0, minutes=60),
            end      = now,
            api_key  = self._api_key,
            secret   = self._secret,
        )

        bundle_bars: dict[str, TickEvent] = {}
        for symbol in self._symbols:
            raw = bars.get(symbol)
            if raw is None:
                continue
            tick = TickEvent(
                symbol    = symbol,
                timestamp = raw["timestamp"],
                open      = raw["open"],
                high      = raw["high"],
                low       = raw["low"],
                close     = raw["close"],
                volume    = raw["volume"],
            )
            self._deques[symbol].append(tick)
            bundle_bars[symbol] = tick

        if bundle_bars:
            ts = next(iter(bundle_bars.values())).timestamp
            self._emit(BarBundleEvent(timestamp=ts, bars=bundle_bars))

        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        dq = self._deques.get(symbol, deque())
        return list(dq)[-n:] if dq else []

    def _seconds_until_next_bar(self) -> float:
        now = datetime.now(tz=ET)
        if self._bar_freq == "1d":
            target = now.replace(hour=_DAILY_BAR_HOUR, minute=_DAILY_BAR_MINUTE,
                                 second=0, microsecond=0)
            if now >= target:
                target += timedelta(days=1)
                while target.weekday() >= 5:   # skip weekends
                    target += timedelta(days=1)
            return max(0.0, (target - now).total_seconds())
        else:
            minutes = int(self._bar_freq.rstrip("m"))
            next_min = ((now.minute // minutes) + 1) * minutes
            delta_min = next_min - now.minute
            target = now.replace(second=0, microsecond=0) + timedelta(minutes=delta_min)
            return max(0.0, (target - now).total_seconds())
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_alpaca_data_handler.py -v`
Expected: all 4 tests **PASS**

- [ ] **Step 4: Commit**

```bash
git add trading/impl/alpaca_data_handler.py tests/test_alpaca_data_handler.py
git commit -m "feat: add AlpacaDataHandler with async bar fetching and shutdown support"
```

---

## Task 6: Alpaca execution handlers

**Files:**
- Create: `trading/impl/alpaca_paper_execution_handler.py`
- Create: `trading/impl/alpaca_execution_handler.py`
- Test: `tests/test_alpaca_execution_handlers.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_alpaca_execution_handlers.py`:

```python
import asyncio
import queue
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.events import FillEvent, OrderEvent


def _order(symbol="AAPL", direction="BUY", qty=10, price=150.0) -> OrderEvent:
    return OrderEvent(
        symbol=symbol,
        timestamp=datetime(2024, 1, 2),
        order_type="MARKET",
        direction=direction,
        quantity=qty,
        reference_price=price,
    )


def test_paper_execute_order_calls_submit_order():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.alpaca_paper_execution_handler.submit_order", return_value="ord-1") as mock_sub:
        handler.execute_order(_order())

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="BUY", quantity=10,
        api_key="key", secret="secret", paper=True,
    )
    assert "ord-1" in handler._pending_orders


def test_live_execute_order_calls_submit_order_with_paper_false():
    from trading.impl.alpaca_execution_handler import AlpacaExecutionHandler

    collected = []
    handler = AlpacaExecutionHandler(
        emit=collected.append,
        api_key="key",
        secret="secret",
    )
    with patch("trading.impl.alpaca_execution_handler.submit_order", return_value="ord-2") as mock_sub:
        handler.execute_order(_order(direction="SELL"))

    mock_sub.assert_called_once_with(
        symbol="AAPL", direction="SELL", quantity=10,
        api_key="key", secret="secret", paper=False,
    )


def test_execute_order_ignores_hold():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler

    collected = []
    handler = AlpacaPaperExecutionHandler(emit=collected.append, api_key="k", secret="s")
    with patch("trading.impl.alpaca_paper_execution_handler.submit_order") as mock_sub:
        handler.execute_order(_order(direction="HOLD", qty=0))

    mock_sub.assert_not_called()
    assert len(collected) == 1  # HOLD FillEvent emitted immediately
    assert collected[0].direction == "HOLD"


@pytest.mark.asyncio
async def test_fill_stream_yields_fill_events_from_websocket():
    from trading.impl.alpaca_paper_execution_handler import AlpacaPaperExecutionHandler
    from trading.events import EventType

    raw_fill = MagicMock()
    raw_fill.event = MagicMock()
    raw_fill.event.__str__ = lambda s: "fill"
    raw_fill.order = MagicMock()
    raw_fill.order.id = "ord-1"
    raw_fill.order.symbol = "AAPL"
    raw_fill.order.side = MagicMock()
    raw_fill.order.side.__str__ = lambda s: "buy"
    raw_fill.order.filled_qty = "10"
    raw_fill.order.filled_avg_price = "150.50"

    ws_queue = asyncio.Queue()
    await ws_queue.put(raw_fill)

    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def _mock_stream(*args, **kwargs):
        yield ws_queue

    handler = AlpacaPaperExecutionHandler(emit=MagicMock(), api_key="k", secret="s")
    handler._pending_orders["ord-1"] = ("AAPL", "BUY", 10)

    with patch("trading.impl.alpaca_paper_execution_handler.open_fill_stream", _mock_stream):
        async with handler.fill_stream() as fill_q:
            fill_event = await asyncio.wait_for(fill_q.get(), timeout=1.0)

    assert fill_event.type == EventType.FILL
    assert fill_event.symbol == "AAPL"
    assert fill_event.direction == "BUY"
    assert fill_event.quantity == 10
    assert fill_event.fill_price == pytest.approx(150.50)
```

Run: `pytest tests/test_alpaca_execution_handlers.py -v`
Expected: **FAIL** — `ModuleNotFoundError`

- [ ] **Step 2: Implement shared base `_AlpacaBaseExecutionHandler`**

The two handlers share all logic except the `paper` flag. Create a private base in `trading/impl/alpaca_paper_execution_handler.py` (paper handler imports it; live handler duplicates minimally):

Create `trading/impl/alpaca_paper_execution_handler.py`:

```python
import asyncio
import contextlib
import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from typing import Callable

from ..base.live.execution import LiveExecutionHandler
from ..events import Event, FillEvent, OrderEvent
from external.alpaca import get_order_status, open_fill_stream, submit_order

logger = logging.getLogger(__name__)

_POLL_INTERVAL = 3.0   # seconds between fallback polls


class AlpacaPaperExecutionHandler(LiveExecutionHandler):
    """Routes orders to Alpaca's paper trading API."""

    _PAPER = True

    def __init__(self, emit: Callable[[Event], None], api_key: str, secret: str):
        super().__init__(emit)
        self._api_key = api_key
        self._secret  = secret
        # order_id → (symbol, direction, quantity)
        self._pending_orders: dict[str, tuple[str, str, int]] = {}
        self._filled_order_ids: set[str] = set()

    def execute_order(self, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            self._emit(FillEvent(
                symbol=event.symbol, timestamp=event.timestamp,
                direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
            ))
            return
        order_id = submit_order(
            symbol=event.symbol,
            direction=event.direction,
            quantity=event.quantity,
            api_key=self._api_key,
            secret=self._secret,
            paper=self._PAPER,
        )
        self._pending_orders[order_id] = (event.symbol, event.direction, event.quantity)

    @asynccontextmanager
    async def fill_stream(self):
        """Yields asyncio.Queue[FillEvent]. Bridges WebSocket stream + polling fallback."""
        fill_q: asyncio.Queue = asyncio.Queue()

        async def _bridge_ws(ws_q: asyncio.Queue):
            while True:
                data = await ws_q.get()
                fill = self._translate(data)
                if fill and fill.symbol and fill.symbol in {s for s, _, _ in self._pending_orders.values()}:
                    self._filled_order_ids.add(str(data.order.id))
                    self._pending_orders.pop(str(data.order.id), None)
                    await fill_q.put(fill)

        async def _poll_fallback():
            while True:
                await asyncio.sleep(_POLL_INTERVAL)
                for order_id, (symbol, direction, qty) in list(self._pending_orders.items()):
                    if order_id in self._filled_order_ids:
                        continue
                    status = get_order_status(order_id, self._api_key, self._secret, self._PAPER)
                    if status and status["status"] == "filled":
                        fill = FillEvent(
                            symbol=symbol,
                            timestamp=datetime.now(timezone.utc),
                            direction=direction,
                            quantity=status["filled_qty"],
                            fill_price=status["filled_avg_price"],
                            commission=0.0,
                        )
                        self._filled_order_ids.add(order_id)
                        self._pending_orders.pop(order_id, None)
                        await fill_q.put(fill)

        async with open_fill_stream(self._api_key, self._secret, paper=self._PAPER) as ws_q:
            ws_task   = asyncio.create_task(_bridge_ws(ws_q))
            poll_task = asyncio.create_task(_poll_fallback())
            try:
                yield fill_q
            finally:
                ws_task.cancel()
                poll_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await ws_task
                with contextlib.suppress(asyncio.CancelledError):
                    await poll_task

    def _translate(self, data) -> FillEvent | None:
        try:
            order     = data.order
            direction = "BUY" if str(order.side) == "buy" else "SELL"
            return FillEvent(
                symbol    = order.symbol,
                timestamp = datetime.now(timezone.utc),
                direction = direction,
                quantity  = int(float(order.filled_qty or 0)),
                fill_price= float(order.filled_avg_price or 0.0),
                commission= 0.0,
            )
        except Exception as exc:
            logger.warning("Failed to translate fill: %s", exc)
            return None
```

- [ ] **Step 3: Implement `AlpacaExecutionHandler` (live)**

Create `trading/impl/alpaca_execution_handler.py`:

```python
from typing import Callable

from ..events import Event
from .alpaca_paper_execution_handler import AlpacaPaperExecutionHandler


class AlpacaExecutionHandler(AlpacaPaperExecutionHandler):
    """Routes orders to Alpaca's live trading API. Identical to paper handler, paper=False."""

    _PAPER = False

    def __init__(self, emit: Callable[[Event], None], api_key: str, secret: str):
        super().__init__(emit=emit, api_key=api_key, secret=secret)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_alpaca_execution_handlers.py -v`
Expected: all 5 tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add trading/impl/alpaca_paper_execution_handler.py \
        trading/impl/alpaca_execution_handler.py \
        tests/test_alpaca_execution_handlers.py
git commit -m "feat: add AlpacaPaperExecutionHandler and AlpacaExecutionHandler with fill stream"
```

---

## Task 7: `AlpacaReconciler`

**Files:**
- Create: `trading/impl/alpaca_reconciler.py`
- Test: `tests/test_alpaca_reconciler.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_alpaca_reconciler.py`:

```python
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_hydrate_calls_portfolio_restore_with_broker_state():
    from trading.impl.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()

    with (
        patch("trading.impl.alpaca_reconciler.get_positions", return_value={"AAPL": 5, "MSFT": 2}),
        patch("trading.impl.alpaca_reconciler.get_account",   return_value=8_500.0),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_portfolio.restore.assert_called_once_with(
        holdings={"AAPL": 5, "MSFT": 2},
        cash=8_500.0,
    )


def test_hydrate_calls_restore_with_empty_positions():
    from trading.impl.alpaca_reconciler import AlpacaReconciler

    reconciler = AlpacaReconciler(api_key="key", secret="secret", paper=True)
    mock_portfolio = MagicMock()

    with (
        patch("trading.impl.alpaca_reconciler.get_positions", return_value={}),
        patch("trading.impl.alpaca_reconciler.get_account",   return_value=10_000.0),
    ):
        asyncio.run(reconciler.hydrate(mock_portfolio))

    mock_portfolio.restore.assert_called_once_with(holdings={}, cash=10_000.0)
```

Run: `pytest tests/test_alpaca_reconciler.py -v`
Expected: **FAIL** — `ModuleNotFoundError`

- [ ] **Step 2: Implement `trading/impl/alpaca_reconciler.py`**

```python
import logging

from ..base.live.reconciler import PositionReconciler
from ..base.portfolio import Portfolio
from external.alpaca import get_account, get_positions

logger = logging.getLogger(__name__)


class AlpacaReconciler(PositionReconciler):
    """Hydrates portfolio state from Alpaca's /positions and /account endpoints."""

    def __init__(self, api_key: str, secret: str, paper: bool):
        self._api_key = api_key
        self._secret  = secret
        self._paper   = paper

    async def hydrate(self, portfolio: Portfolio) -> None:
        holdings = get_positions(self._api_key, self._secret, self._paper)
        cash     = get_account(self._api_key,   self._secret, self._paper)
        logger.info("Reconciled: %d positions, cash=%.2f", len(holdings), cash)
        portfolio.restore(holdings=holdings, cash=cash)
```

- [ ] **Step 3: Run tests**

Run: `pytest tests/test_alpaca_reconciler.py -v`
Expected: both tests **PASS**

- [ ] **Step 4: Commit**

```bash
git add trading/impl/alpaca_reconciler.py tests/test_alpaca_reconciler.py
git commit -m "feat: add AlpacaReconciler — hydrates portfolio from broker on startup"
```

---

## Task 8: `LiveRunner`

**Files:**
- Create: `trading/impl/live_runner.py`
- Test: `tests/test_live_runner.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_live_runner.py`:

```python
import asyncio
import queue
from contextlib import asynccontextmanager
from datetime import datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from trading.events import (
    BarBundleEvent, EventType, FillEvent, OrderEvent,
    SignalEvent, StrategyBundleEvent, TickEvent,
)


def _bar_bundle():
    ts = datetime(2024, 1, 2, 16, 5)
    tick = TickEvent(symbol="AAPL", timestamp=ts,
                     open=150.0, high=151.0, low=149.0, close=150.0, volume=1000.0)
    return BarBundleEvent(timestamp=ts, bars={"AAPL": tick})


@asynccontextmanager
async def _null_fill_stream():
    yield asyncio.Queue()   # empty queue — no fills arrive


@pytest.mark.asyncio
async def test_runner_calls_reconciler_hydrate_before_first_bar():
    from trading.impl.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)  # stop immediately
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    reconciler.hydrate.assert_called_once_with(portfolio)


@pytest.mark.asyncio
async def test_runner_dispatches_bar_bundle_to_portfolio_and_strategy():
    from trading.impl.live_runner import LiveRunner

    events = queue.Queue()
    bundle = _bar_bundle()
    events.put(bundle)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1   # True first call, False second
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    portfolio.fill_pending_orders.assert_called_once_with(bundle)
    strategy.get_signals.assert_called_once_with(bundle)


@pytest.mark.asyncio
async def test_runner_dispatches_order_to_execution():
    from trading.impl.live_runner import LiveRunner

    events = queue.Queue()
    ts = datetime(2024, 1, 2, 16, 5)
    order = OrderEvent(symbol="AAPL", timestamp=ts, order_type="MARKET",
                       direction="BUY", quantity=5)
    events.put(order)

    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        return call_count == 1
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    execution.execute_order.assert_called_once_with(order)


@pytest.mark.asyncio
async def test_runner_puts_fill_events_from_stream_onto_queue():
    from trading.impl.live_runner import LiveRunner

    fill_event = FillEvent(
        symbol="AAPL", timestamp=datetime(2024, 1, 2, 16, 5),
        direction="BUY", quantity=5, fill_price=150.0, commission=0.0,
    )

    @asynccontextmanager
    async def _fill_stream_with_one_fill():
        q = asyncio.Queue()
        await q.put(fill_event)
        yield q

    events = queue.Queue()
    data = MagicMock()
    call_count = 0
    async def _update():
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(0.01)   # give drain task time to forward the fill
        return call_count == 1
    data.update_bars_async = _update

    strategy  = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _fill_stream_with_one_fill
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    portfolio.on_fill.assert_called_once_with(fill_event)
```

Run: `pytest tests/test_live_runner.py -v`
Expected: **FAIL** — `ModuleNotFoundError`

- [ ] **Step 2: Add `pytest.ini` configuration for asyncio**

If `pytest.ini` or `pyproject.toml` does not exist, create `pytest.ini` in project root:

```ini
[pytest]
asyncio_mode = auto
```

- [ ] **Step 3: Implement `trading/impl/live_runner.py`**

```python
import asyncio
import logging
import queue
import signal

from ..base.live.execution  import LiveExecutionHandler
from ..base.live.reconciler import PositionReconciler
from ..base.live.runner     import LiveRunner as LiveRunnerBase
from ..base.portfolio       import Portfolio
from ..base.strategy        import StrategySignalGenerator
from ..base.data            import DataHandler
from ..events               import EventType

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
        events:     queue.Queue,
        data:       DataHandler,
        strategy:   StrategySignalGenerator,
        portfolio:  Portfolio,
        execution:  LiveExecutionHandler,
        reconciler: PositionReconciler,
    ):
        self._events     = events
        self._data       = data
        self._strategy   = strategy
        self._portfolio  = portfolio
        self._execution  = execution
        self._reconciler = reconciler
        self._shutdown   = False

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, self._request_shutdown)

        await self._reconciler.hydrate(self._portfolio)

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
                self._portfolio.on_signal(event)
            case EventType.ORDER:
                self._execution.execute_order(event)
            case EventType.FILL:
                self._portfolio.on_fill(event)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_live_runner.py -v`
Expected: all 4 tests **PASS**

Run: `pytest tests/ -v --ignore=tests/test_yahoo_external.py --ignore=tests/test_index_constituents_external.py`
Expected: all tests **PASS**

- [ ] **Step 5: Commit**

```bash
git add trading/impl/live_runner.py tests/test_live_runner.py pytest.ini
git commit -m "feat: add LiveRunner — asyncio loop with fill stream drain and graceful shutdown"
```

---

## Task 9: Exports + `run_live.py`

**Files:**
- Modify: `trading/impl/__init__.py`
- Create: `run_live.py`
- Modify: `requirements.txt` (already done in Task 2)

- [ ] **Step 1: Update `trading/impl/__init__.py`**

```python
from .alpaca_data_handler              import AlpacaDataHandler
from .alpaca_execution_handler         import AlpacaExecutionHandler
from .alpaca_paper_execution_handler   import AlpacaPaperExecutionHandler
from .alpaca_reconciler                import AlpacaReconciler
from .index_constituents_universe_builder import IndexConstituentsUniverseBuilder
from .json_strategy_params_loader      import JsonStrategyParamsLoader
from .live_runner                      import LiveRunner
from .multi_csv_data_handler           import MultiCSVDataHandler
from .risk_guard                       import RiskGuard
from .simulated_execution_handler      import SimulatedExecutionHandler
from .simple_portfolio                 import SimplePortfolio
from .strategy_container               import StrategyContainer
from .yahoo_data_handler               import YahooDataHandler

__all__ = [
    "AlpacaDataHandler",
    "AlpacaExecutionHandler",
    "AlpacaPaperExecutionHandler",
    "AlpacaReconciler",
    "IndexConstituentsUniverseBuilder",
    "JsonStrategyParamsLoader",
    "LiveRunner",
    "MultiCSVDataHandler",
    "RiskGuard",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "StrategyContainer",
    "YahooDataHandler",
]
```

- [ ] **Step 2: Create `run_live.py`**

```python
"""
Live / paper trading entry point.
Set MODE = "paper" to route orders to Alpaca's paper API (default).
Set MODE = "live"  to route orders to Alpaca's live API (real capital).

Credentials are loaded from environment variables:
  ALPACA_API_KEY, ALPACA_SECRET_KEY
  (For live mode the same vars are used; Alpaca distinguishes paper vs live
  via the paper= flag, not separate credentials.)

Strategy params are loaded from strategy_params/ exactly as in run_backtest.py.
"""
import asyncio
import os
import queue

from trading.impl import (
    AlpacaDataHandler,
    AlpacaExecutionHandler,
    AlpacaPaperExecutionHandler,
    AlpacaReconciler,
    JsonStrategyParamsLoader,
    LiveRunner,
    RiskGuard,
    SimplePortfolio,
    StrategyContainer,
)

# --- Configuration -----------------------------------------------------------
MODE               = "paper"            # "paper" | "live"
BAR_FREQ           = "1d"               # "1d" for daily, "5m" for 5-minute intraday
STRATEGY_PARAMS_DIR = "strategy_params"
INITIAL_CAPITAL    = 10_000.0
MAX_LEVERAGE       = 1.0
FILL_COST_BUFFER   = 0.002
MAX_DAILY_LOSS_PCT = 0.05               # halt if equity drops 5% from day open
MAX_POSITION_PCT   = 0.20              # cap any single position at 20% of equity
# -----------------------------------------------------------------------------

API_KEY = os.environ["ALPACA_API_KEY"]
SECRET  = os.environ["ALPACA_SECRET_KEY"]

events   = queue.Queue()
data     = None   # resolved after strategy symbols are known

loader   = JsonStrategyParamsLoader(STRATEGY_PARAMS_DIR)
strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
for strategy_cls, params in loader.load_all():
    strategy.add(strategy_cls, params)

symbols = strategy.symbols

data = AlpacaDataHandler(
    emit     = events.put,
    symbols  = symbols,
    bar_freq = BAR_FREQ,
    api_key  = API_KEY,
    secret   = SECRET,
)

execution = (
    AlpacaPaperExecutionHandler(events.put, api_key=API_KEY, secret=SECRET)
    if MODE == "paper"
    else AlpacaExecutionHandler(events.put, api_key=API_KEY, secret=SECRET)
)

risk_guard = RiskGuard(
    max_daily_loss_pct = MAX_DAILY_LOSS_PCT,
    max_position_pct   = MAX_POSITION_PCT,
    initial_capital    = INITIAL_CAPITAL,
)

reconciler = AlpacaReconciler(api_key=API_KEY, secret=SECRET, paper=(MODE == "paper"))

portfolio = SimplePortfolio(
    emit             = events.put,
    get_bars         = data.get_latest_bars,
    symbols          = symbols,
    initial_capital  = INITIAL_CAPITAL,
    max_leverage     = MAX_LEVERAGE,
    fill_cost_buffer = FILL_COST_BUFFER,
    risk_guard       = risk_guard,
)

runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)

if __name__ == "__main__":
    asyncio.run(runner.run())
```

- [ ] **Step 3: Verify full test suite passes**

Run: `pytest tests/ -v --ignore=tests/test_yahoo_external.py --ignore=tests/test_index_constituents_external.py`
Expected: all tests **PASS**, no regressions

- [ ] **Step 4: Commit**

```bash
git add trading/impl/__init__.py run_live.py
git commit -m "feat: wire run_live.py and update trading/impl exports"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Implemented in |
|---|---|
| `DataHandler.update_bars_async()` default | Task 1 |
| `ExecutionHandler.execute_order_async()` default | Task 1 |
| `Portfolio.restore()` abstract method | Task 1 |
| `LiveRunner`, `RiskGuard`, `PositionReconciler`, `LiveExecutionHandler` ABCs | Task 1 |
| `external/alpaca.py` wrappers | Task 2 |
| `RiskGuard` daily loss limit + per-symbol cap + auto-reset | Task 3 |
| `SimplePortfolio.restore()` + `risk_guard` injection in `on_signal()` | Task 4 |
| `AlpacaDataHandler` async bar fetching + shutdown | Task 5 |
| `AlpacaPaperExecutionHandler` + `AlpacaExecutionHandler` + fill stream + polling fallback | Task 6 |
| `AlpacaReconciler.hydrate()` | Task 7 |
| `LiveRunner` asyncio loop + reconcile-on-start + fill stream drain + SIGTERM | Task 8 |
| `run_live.py` wiring | Task 9 |
| Module boundaries (impl uses external/ only) | Enforced throughout |
| Paper vs live swap at wiring point only | Task 9 |

All spec requirements covered. No gaps found.
