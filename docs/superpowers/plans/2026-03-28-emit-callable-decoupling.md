# Emit Callable Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace `events: queue.Queue` with `emit: Callable[[Event], None]` across all four components so each component depends only on a plain function, not a queue.

**Architecture:** Each ABC gains `__init__(emit)` to store `self._emit`; concrete classes call `super().__init__(emit)` and replace every `self._events.put(X)` with `self._emit(X)`. Strategy gets special treatment: `calculate_signals` becomes a pure method returning `SignalBundleEvent | None`, and a new `get_signals` ABC method wraps it and emits the result. The backtester calls `get_signals` instead of `calculate_signals`. `run_backtest.py` passes `events.put` to all constructors.

**Tech Stack:** Python 3.10+ stdlib only. `pytest` for tests. `queue.Queue` is still owned by the `Backtester` — components no longer import it.

---

### Task 1: Update Strategy ABC

**Files:**
- Modify: `trading/base/strategy.py`
- Test: `tests/test_strategy.py`

- [ ] **Step 1: Write a failing test for get_signals**

Add this test to `tests/test_strategy.py` (after the existing `test_strategy_abc_exposes_get_bars` test):

```python
def test_get_signals_emits_when_calculate_signals_returns_bundle():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)
    bundle = _bundle(["AAPL"])
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG")
    result = SignalBundleEvent(timestamp=ts, signals={"AAPL": sig})

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return result

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(bundle)
    assert collected == [result]


def test_get_signals_does_not_emit_when_calculate_signals_returns_none():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(_bundle(["AAPL"]))
    assert collected == []
```

- [ ] **Step 2: Run to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py::test_get_signals_emits_when_calculate_signals_returns_bundle tests/test_strategy.py::test_get_signals_does_not_emit_when_calculate_signals_returns_none -v
```

Expected: FAIL — `Strategy.__init__` doesn't accept `emit`, `get_signals` doesn't exist.

- [ ] **Step 3: Replace trading/base/strategy.py**

```python
from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, Event, SignalBundleEvent, TickEvent


class Strategy(ABC):
    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        self._emit     = emit
        self._get_bars = get_bars

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    def get_signals(self, event: BarBundleEvent) -> None:
        result = self.calculate_signals(event)
        if result is not None:
            self._emit(result)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        """Compute signals from a bar bundle. Return a SignalBundleEvent or None."""
        ...
```

- [ ] **Step 4: Run the two new tests**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py::test_get_signals_emits_when_calculate_signals_returns_bundle tests/test_strategy.py::test_get_signals_does_not_emit_when_calculate_signals_returns_none -v
```

Expected: PASS. (The existing strategy tests will fail now — fixed in Task 2.)

- [ ] **Step 5: Commit**

```bash
git add trading/base/strategy.py tests/test_strategy.py
git commit -m "feat: Strategy ABC accepts emit callable, adds get_signals wrapper"
```

---

### Task 2: Update SMACrossoverStrategy and all strategy tests

**Files:**
- Modify: `trading/impl/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Replace tests/test_strategy.py entirely**

```python
import queue
from datetime import datetime
from trading.base.strategy import Strategy
from trading.impl.strategy import SMACrossoverStrategy
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


def _bars(closes: list[float]) -> list[TickEvent]:
    return [TickEvent(symbol="", timestamp=datetime(2020, 1, 2), open=c, high=c, low=c, close=c, volume=1000.0) for c in closes]


def _bundle(symbols: list[str], close: float = 100.0) -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={s: TickEvent(symbol=s, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000.0)
              for s in symbols},
    )


def test_strategy_abc_exposes_get_bars():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    stub = _Stub(emit=lambda e: None, get_bars=lambda s, n: [tick])
    assert stub.get_bars("AAPL", 1) == [tick]


def test_get_signals_emits_when_calculate_signals_returns_bundle():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG")
    result = SignalBundleEvent(timestamp=ts, signals={"AAPL": sig})

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return result

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(_bundle(["AAPL"]))
    assert collected == [result]


def test_get_signals_does_not_emit_when_calculate_signals_returns_none():
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
            return None

    collected = []
    stub = _Stub(emit=collected.append, get_bars=lambda s, n: [tick])
    stub.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_no_signal_before_enough_history():
    collected = []
    bars = _bars([100.0] * 5)
    strategy = SMACrossoverStrategy(lambda e: None, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_long_signal_when_fast_above_slow():
    collected = []
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1
    assert isinstance(collected[0], SignalBundleEvent)
    assert collected[0].signals["AAPL"].signal_type == "LONG"


def test_no_duplicate_long_signal():
    collected = []
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert len(collected) == 1  # no second emit


def test_exit_signal_when_fast_below_slow():
    collected = []
    current_bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL"], get_bars=lambda s, n: current_bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"], close=110.0))
    assert collected[-1].signals["AAPL"].signal_type == "LONG"

    current_bars = _bars([110.0] * 20 + [90.0] * 10)
    strategy.get_signals(_bundle(["AAPL"], close=90.0))
    assert collected[-1].signals["AAPL"].signal_type == "EXIT"


def test_no_signal_when_flat():
    collected = []
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(lambda e: None, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_multi_symbol_signals_are_independent():
    collected = []
    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)
        return _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(collected.append, ["AAPL", "MSFT"], get_bars=get_bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 1
    assert "AAPL" in collected[0].signals
    assert "MSFT" not in collected[0].signals


def test_no_emission_when_no_symbol_signals():
    collected = []
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(lambda e: None, ["AAPL", "MSFT"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.get_signals(_bundle(["AAPL", "MSFT"]))
    assert collected == []
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py -v
```

Expected: most tests FAIL — `SMACrossoverStrategy` still takes `queue.Queue` as first arg.

- [ ] **Step 3: Replace trading/impl/strategy.py**

```python
from typing import Callable

from ..base.strategy import Strategy
from ..events import BarBundleEvent, Event, SignalBundleEvent, SignalEvent, TickEvent


class SMACrossoverStrategy(Strategy):
    """
    Emits LONG when the fast SMA crosses above the slow SMA for a symbol.
    Emits EXIT when the fast SMA crosses below the slow SMA.
    Operates on multiple symbols simultaneously.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        symbols:  list[str],
        get_bars: Callable[[str, int], list[TickEvent]],
        fast:     int = 10,
        slow:     int = 30,
    ):
        super().__init__(emit, get_bars)
        self._symbols  = symbols
        self._fast     = fast
        self._slow     = slow
        self._position: dict[str, str | None] = {s: None for s in symbols}

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        signals: dict[str, SignalEvent] = {}

        for symbol in self._symbols:
            bars = self.get_bars(symbol, self._slow)
            if len(bars) < self._slow:
                continue

            closes   = [b.close for b in bars]
            fast_sma = sum(closes[-self._fast:]) / self._fast
            slow_sma = sum(closes) / self._slow

            if fast_sma > slow_sma and self._position[symbol] != "LONG":
                self._position[symbol] = "LONG"
                signals[symbol] = SignalEvent(
                    symbol      = symbol,
                    timestamp   = event.timestamp,
                    signal_type = "LONG",
                )
            elif fast_sma < slow_sma and self._position[symbol] == "LONG":
                self._position[symbol] = None
                signals[symbol] = SignalEvent(
                    symbol      = symbol,
                    timestamp   = event.timestamp,
                    signal_type = "EXIT",
                )

        return SignalBundleEvent(timestamp=event.timestamp, signals=signals) if signals else None
```

- [ ] **Step 4: Run all strategy tests**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py -v
```

Expected: all 10 PASS.

- [ ] **Step 5: Commit**

```bash
git add trading/impl/strategy.py tests/test_strategy.py
git commit -m "feat: SMACrossoverStrategy uses emit callable, calculate_signals returns bundle"
```

---

### Task 3: Update Portfolio ABC and SimplePortfolio

**Files:**
- Modify: `trading/base/portfolio.py`
- Modify: `trading/impl/portfolio.py`
- Modify: `tests/test_portfolio.py`

- [ ] **Step 1: Write failing test**

At the top of `tests/test_portfolio.py`, add this test after the imports:

```python
def test_portfolio_constructor_accepts_emit_callable():
    collected = []
    def get_bars(symbol, n=1):
        return [TickEvent(symbol=symbol, timestamp=datetime(2020, 1, 2), open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0)]
    portfolio = SimplePortfolio(collected.append, get_bars, ["AAPL"], initial_capital=10_000.0)
    assert portfolio is not None
```

- [ ] **Step 2: Run to confirm it fails**

```bash
source .venv/bin/activate && pytest tests/test_portfolio.py::test_portfolio_constructor_accepts_emit_callable -v
```

Expected: FAIL — `SimplePortfolio` still expects `queue.Queue` as first arg.

- [ ] **Step 3: Replace trading/base/portfolio.py**

```python
from abc import ABC, abstractmethod
from typing import Callable

from ..events import Event, FillEvent, SignalBundleEvent


class Portfolio(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

    @abstractmethod
    def on_signal(self, event: SignalBundleEvent) -> None: ...

    @abstractmethod
    def on_fill(self, event: FillEvent) -> None: ...

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...
```

- [ ] **Step 4: Replace trading/impl/portfolio.py**

```python
from typing import Callable

from ..base.portfolio import Portfolio
from ..events import Event, FillEvent, OrderEvent, SignalBundleEvent, TickEvent


class SimplePortfolio(Portfolio):
    """
    Sizes every entry as 100% of available cash per symbol (first LONG wins if multiple arrive).
    Tracks cash, per-symbol holdings, and records equity snapshots on every fill.
    """

    def __init__(
        self,
        emit:            Callable[[Event], None],
        get_bars:        Callable[[str, int], list[TickEvent]],
        symbols:         list[str],
        initial_capital: float = 10_000.0,
    ):
        super().__init__(emit)
        self._get_bars        = get_bars
        self._symbols         = symbols
        self._cash            = initial_capital
        self._initial_capital = initial_capital
        self._holdings: dict[str, int] = {s: 0 for s in symbols}
        self._equity_curve: list[dict] = []

    def on_signal(self, event: SignalBundleEvent) -> None:
        available_cash = self._cash
        for symbol, signal in event.signals.items():
            bars = self._get_bars(symbol, 1)
            if not bars:
                continue
            price = bars[-1].close

            if signal.signal_type == "LONG" and self._holdings[symbol] == 0:
                quantity = int(available_cash // price)
                if quantity > 0:
                    available_cash -= quantity * price
                    self._emit(OrderEvent(
                        symbol          = symbol,
                        timestamp       = event.timestamp,
                        order_type      = "MARKET",
                        direction       = "BUY",
                        quantity        = quantity,
                        reference_price = price,
                    ))

            elif signal.signal_type == "EXIT" and self._holdings[symbol] > 0:
                self._emit(OrderEvent(
                    symbol          = symbol,
                    timestamp       = event.timestamp,
                    order_type      = "MARKET",
                    direction       = "SELL",
                    quantity        = self._holdings[symbol],
                    reference_price = price,
                ))

    def on_fill(self, event: FillEvent) -> None:
        multiplier = 1 if event.direction == "BUY" else -1
        self._holdings[event.symbol] += multiplier * event.quantity
        self._cash -= multiplier * event.fill_price * event.quantity + event.commission

        market_value = 0.0
        for symbol in self._symbols:
            bars = self._get_bars(symbol, 1)
            if bars:
                market_value += self._holdings[symbol] * bars[-1].close

        self._equity_curve.append({
            "timestamp":    event.timestamp,
            "cash":         self._cash,
            "holdings":     dict(self._holdings),
            "market_value": market_value,
            "equity":       self._cash + market_value,
        })

    @property
    def equity_curve(self) -> list[dict]:
        return self._equity_curve
```

- [ ] **Step 5: Replace tests/test_portfolio.py**

```python
from datetime import datetime

from trading.impl.portfolio import SimplePortfolio
from trading.events import FillEvent, OrderEvent, SignalBundleEvent, SignalEvent, TickEvent


def _get_bars(prices: dict[str, float]):
    def get_bars(symbol, n=1):
        p = prices[symbol]
        return [TickEvent(symbol=symbol, timestamp=datetime(2020, 1, 2), open=p, high=p, low=p, close=p, volume=1000.0)]
    return get_bars


def _signal_bundle(symbol: str, signal_type: str, ts=None) -> SignalBundleEvent:
    ts = ts or datetime(2020, 1, 2)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal_type=signal_type)
    return SignalBundleEvent(timestamp=ts, signals={symbol: sig})


def _fill(symbol: str, direction: str, quantity: int, price: float) -> FillEvent:
    return FillEvent(
        symbol=symbol, timestamp=datetime(2020, 1, 2),
        direction=direction, quantity=quantity,
        fill_price=price, commission=1.0,
    )


def test_portfolio_constructor_accepts_emit_callable():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    assert portfolio is not None


def test_long_signal_emits_buy_order():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))

    assert len(collected) == 1
    order = collected[0]
    assert isinstance(order, OrderEvent)
    assert order.symbol == "AAPL"
    assert order.direction == "BUY"
    assert order.quantity == 100   # 10_000 // 100


def test_long_signal_no_order_when_already_holding():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))
    assert collected == []


def test_exit_signal_emits_sell_order():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_signal_bundle("AAPL", "EXIT"))
    assert len(collected) == 1
    assert collected[0].direction == "SELL"
    assert collected[0].quantity == 50


def test_exit_signal_no_order_when_no_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_signal_bundle("AAPL", "EXIT"))
    assert collected == []


def test_on_fill_updates_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 50


def test_on_fill_sell_decreases_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 0


def test_equity_sums_all_symbol_holdings():
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 200.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))
    snapshot = portfolio.equity_curve[-1]
    assert snapshot["market_value"] == 1000.0
    assert snapshot["holdings"] == {"AAPL": 10, "MSFT": 0}


def test_long_signal_no_order_when_no_cash():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=50.0)

    portfolio.on_signal(_signal_bundle("AAPL", "LONG"))
    assert collected == []


def test_multi_symbol_long_does_not_overdraw_cash():
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = SignalBundleEvent(
        timestamp=ts,
        signals={
            "AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal_type="LONG"),
            "MSFT": SignalEvent(symbol="MSFT", timestamp=ts, signal_type="LONG"),
        },
    )
    portfolio.on_signal(bundle)

    total_order_value = sum(o.quantity * o.reference_price for o in collected)
    assert total_order_value <= 10_000.0, f"Orders exceed cash: {total_order_value}"
```

- [ ] **Step 6: Run all portfolio tests**

```bash
source .venv/bin/activate && pytest tests/test_portfolio.py -v
```

Expected: all 10 PASS.

- [ ] **Step 7: Commit**

```bash
git add trading/base/portfolio.py trading/impl/portfolio.py tests/test_portfolio.py
git commit -m "feat: Portfolio uses emit callable, drops queue.Queue dependency"
```

---

### Task 4: Update ExecutionHandler ABC and SimulatedExecutionHandler

**Files:**
- Modify: `trading/base/execution.py`
- Modify: `trading/impl/execution.py`

(ExecutionHandler is covered by `test_backtester.py` via integration — no standalone test file exists. The end-to-end backtest in Task 7 is the verification.)

- [ ] **Step 1: Replace trading/base/execution.py**

```python
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
```

- [ ] **Step 2: Replace trading/impl/execution.py**

```python
from typing import Callable

from ..base.execution import ExecutionHandler
from ..events import Event, FillEvent, OrderEvent


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Fills at reference_price (current bar close) with slippage and flat commission.
    BUYs fill slightly higher, SELLs slightly lower.
    """

    def __init__(
        self,
        emit:         Callable[[Event], None],
        commission:   float = 1.0,
        slippage_pct: float = 0.0005,
    ):
        super().__init__(emit)
        self._commission   = commission
        self._slippage_pct = slippage_pct

    def execute_order(self, event: OrderEvent) -> None:
        direction_factor = 1 if event.direction == "BUY" else -1
        fill_price = event.reference_price * (1 + direction_factor * self._slippage_pct)

        self._emit(FillEvent(
            symbol     = event.symbol,
            timestamp  = event.timestamp,
            direction  = event.direction,
            quantity   = event.quantity,
            fill_price = fill_price,
            commission = self._commission,
        ))
```

- [ ] **Step 3: Run the existing test suite to check nothing broke**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests that passed before still pass. `test_backtester.py` may fail — that is fixed in Task 6.

- [ ] **Step 4: Commit**

```bash
git add trading/base/execution.py trading/impl/execution.py
git commit -m "feat: ExecutionHandler uses emit callable, drops queue.Queue dependency"
```

---

### Task 5: Update DataHandler ABC and MultiCSVDataHandler

**Files:**
- Modify: `trading/base/data.py`
- Modify: `trading/impl/data.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Write a failing test**

In `tests/test_data.py`, change the first test's setup to use `events.put` instead of `events`:

```python
def test_update_bars_emits_bar_bundle_event():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        ...
```

Run it — it will fail because `MultiCSVDataHandler` still expects a `queue.Queue` object, not a callable.

```bash
source .venv/bin/activate && pytest tests/test_data.py::test_update_bars_emits_bar_bundle_event -v
```

Expected: FAIL — `queue.Queue.put` is called as a method but the constructor stores it as `self._events` and calls `self._events.put(...)`, which would be `events.put.put(...)`.

- [ ] **Step 2: Replace trading/base/data.py**

```python
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
```

- [ ] **Step 3: Replace trading/impl/data.py**

```python
import csv
from collections import deque
from datetime import datetime
from typing import Callable

from ..base.data import DataHandler
from ..events import BarBundleEvent, Event, TickEvent


class MultiCSVDataHandler(DataHandler):
    """
    Loads N CSVs (one per symbol), computes the union of all timestamps,
    and replays one BarBundleEvent per timestep. Missing bars are zero-filled.
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        csv_paths:   list[str],
        max_history: int = 200,
        date_format: str = "%Y-%m-%d",
    ):
        if len(symbols) != len(csv_paths):
            raise ValueError(
                f"symbols and csv_paths must have the same length "
                f"(got {len(symbols)} and {len(csv_paths)})"
            )
        super().__init__(emit)
        self._symbols = symbols

        raw: dict[str, dict[datetime, TickEvent]] = {}
        for symbol, path in zip(symbols, csv_paths):
            raw[symbol] = self._load(symbol, path, date_format)

        all_ts: set[datetime] = set()
        for data in raw.values():
            all_ts.update(data.keys())
        timeline = sorted(all_ts)

        self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
        for ts in timeline:
            bundle = {
                symbol: raw[symbol].get(
                    ts,
                    TickEvent(symbol=symbol, timestamp=ts, open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0),
                )
                for symbol in symbols
            }
            self._merged.append((ts, bundle))

        self._index = 0
        self._history: dict[str, deque] = {
            s: deque(maxlen=max_history) for s in symbols
        }

    def _load(self, symbol: str, path: str, date_format: str) -> dict[datetime, TickEvent]:
        result: dict[datetime, TickEvent] = {}
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = datetime.strptime(row["timestamp"], date_format)
                result[ts] = TickEvent(
                    symbol    = symbol,
                    timestamp = ts,
                    open      = float(row["open"]),
                    high      = float(row["high"]),
                    low       = float(row["low"]),
                    close     = float(row["close"]),
                    volume    = float(row["volume"]),
                )
        return result

    def update_bars(self) -> bool:
        if self._index >= len(self._merged):
            return False
        ts, bars = self._merged[self._index]
        self._index += 1
        for symbol, bar in bars.items():
            self._history[symbol].append(bar)
        self._emit(BarBundleEvent(timestamp=ts, bars=bars))
        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        bars = list(self._history[symbol])
        return bars[-n:] if len(bars) >= n else bars
```

- [ ] **Step 4: Update tests/test_data.py — replace every `MultiCSVDataHandler(events,` with `MultiCSVDataHandler(events.put,`**

The full updated file (only the constructor calls change — all `events.get_nowait()` calls remain valid since `events.put` still puts into `events`):

```python
import csv
import os
import queue
import tempfile
from datetime import datetime

from trading.impl.data import MultiCSVDataHandler
from trading.events import BarBundleEvent, EventType


def make_csv(rows: list[dict]) -> str:
    f = tempfile.NamedTemporaryFile(
        mode="w", suffix=".csv", delete=False, newline=""
    )
    writer = csv.DictWriter(
        f, fieldnames=["timestamp", "open", "high", "low", "close", "volume"]
    )
    writer.writeheader()
    writer.writerows(rows)
    f.close()
    return f.name


AAPL_ROWS = [
    {"timestamp": "2020-01-02", "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000},
    {"timestamp": "2020-01-03", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1100},
]
MSFT_ROWS = [
    {"timestamp": "2020-01-02", "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2000},
    {"timestamp": "2020-01-04", "open": 200.5, "high": 202.0, "low": 200.0, "close": 201.0, "volume": 2100},
]


def test_update_bars_emits_bar_bundle_event():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        assert handler.update_bars() is True
        event = events.get_nowait()
        assert isinstance(event, BarBundleEvent)
        assert event.type == EventType.BAR_BUNDLE
        assert "AAPL" in event.bars
        assert "MSFT" in event.bars
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_timestamps_are_union_sorted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        count = 0
        while handler.update_bars():
            count += 1
        assert count == 3
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_missing_symbol_bar_is_zero_filled():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        events.get_nowait()
        handler.update_bars()
        bundle = events.get_nowait()
        assert bundle.bars["AAPL"].close == 101.0
        assert bundle.bars["MSFT"].close == 0.0
        assert bundle.bars["MSFT"].open == 0.0
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_present_bars_have_correct_values():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        bundle = events.get_nowait()
        assert bundle.bars["AAPL"].close == 100.5
        assert bundle.bars["MSFT"].close == 200.5
        assert bundle.timestamp == datetime(2020, 1, 2)
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_get_latest_bars_returns_history():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        handler.update_bars()
        bars = handler.get_latest_bars("AAPL", 2)
        assert len(bars) == 2
        assert bars[-1].close == 101.0
        assert bars[0].close == 100.5
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_get_latest_bars_partial_history():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        bars = handler.get_latest_bars("AAPL", 10)
        assert len(bars) == 1
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_update_bars_returns_false_when_exhausted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()
        handler.update_bars()
        handler.update_bars()
        assert handler.update_bars() is False
    finally:
        os.unlink(aapl)
        os.unlink(msft)
```

- [ ] **Step 5: Run all data tests**

```bash
source .venv/bin/activate && pytest tests/test_data.py -v
```

Expected: all 7 PASS.

- [ ] **Step 6: Commit**

```bash
git add trading/base/data.py trading/impl/data.py tests/test_data.py
git commit -m "feat: DataHandler uses emit callable, drops queue.Queue dependency"
```

---

### Task 6: Update Backtester and its tests

**Files:**
- Modify: `trading/backtester.py`
- Modify: `tests/test_backtester.py`

- [ ] **Step 1: Write failing test**

In `tests/test_backtester.py`, change `test_bar_bundle_routes_to_strategy` to assert on `get_signals` instead of `calculate_signals`:

```python
def test_bar_bundle_routes_to_strategy():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    bundle = _bar_bundle()
    events.put(bundle)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    strategy.get_signals.assert_called_once_with(bundle)
```

- [ ] **Step 2: Run to confirm it fails**

```bash
source .venv/bin/activate && pytest tests/test_backtester.py::test_bar_bundle_routes_to_strategy -v
```

Expected: FAIL — backtester still calls `calculate_signals`.

- [ ] **Step 3: Update trading/backtester.py — replace both calculate_signals calls with get_signals**

Replace the entire file:

```python
import queue

from .base.data      import DataHandler
from .base.execution import ExecutionHandler
from .base.portfolio import Portfolio
from .base.strategy  import Strategy
from .events         import EventType


class Backtester:
    def __init__(
        self,
        events:    queue.Queue,
        data:      DataHandler,
        strategy:  Strategy,
        portfolio: Portfolio,
        execution: ExecutionHandler,
    ):
        self._events    = events
        self._data      = data
        self._strategy  = strategy
        self._portfolio = portfolio
        self._execution = execution

    def run(self) -> None:
        while True:
            # Drain the event queue fully before advancing to the next bar
            while not self._events.empty():
                event = self._events.get(block=False)
                match event.type:
                    case EventType.BAR_BUNDLE:
                        self._strategy.get_signals(event)
                    case EventType.SIGNAL_BUNDLE:
                        self._portfolio.on_signal(event)
                    case EventType.ORDER:
                        self._execution.execute_order(event)
                    case EventType.FILL:
                        self._portfolio.on_fill(event)

            # Advance to the next bar; stop when data is exhausted
            if not self._data.update_bars():
                break

        # Drain any remaining events after the last bar
        while not self._events.empty():
            event = self._events.get(block=False)
            match event.type:
                case EventType.BAR_BUNDLE:
                    self._strategy.get_signals(event)
                case EventType.SIGNAL_BUNDLE:
                    self._portfolio.on_signal(event)
                case EventType.ORDER:
                    self._execution.execute_order(event)
                case EventType.FILL:
                    self._portfolio.on_fill(event)
```

- [ ] **Step 4: Run all backtester tests**

```bash
source .venv/bin/activate && pytest tests/test_backtester.py -v
```

Expected: all 4 PASS.

- [ ] **Step 5: Run the full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add trading/backtester.py tests/test_backtester.py
git commit -m "feat: backtester dispatches get_signals instead of calculate_signals"
```

---

### Task 7: Update run_backtest.py and verify end-to-end

**Files:**
- Modify: `run_backtest.py`

- [ ] **Step 1: Update the wiring in run_backtest.py**

Replace lines 27–30 with:

```python
events    = queue.Queue()
data      = MultiCSVDataHandler(events.put, SYMBOLS, CSV_PATHS)
strategy  = SMACrossoverStrategy(events.put, SYMBOLS, data.get_latest_bars, fast=FAST_WINDOW, slow=SLOW_WINDOW)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, SYMBOLS, initial_capital=INITIAL_CAPITAL)
execution = SimulatedExecutionHandler(events.put, commission=COMMISSION, slippage_pct=SLIPPAGE_PCT)
```

- [ ] **Step 2: Run the full test suite one final time**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests PASS.

- [ ] **Step 3: Run the backtest end-to-end**

```bash
source .venv/bin/activate && python run_backtest.py
```

Expected output:
```
Initial capital : $ 10,000.00
Final equity    : $  7,834.38
Total return    : -21.66%
Trades (fills)  : 28
Equity curve    : results/equity_curve.csv
```

- [ ] **Step 4: Commit**

```bash
git add run_backtest.py
git commit -m "feat: wire all components with emit callable instead of queue.Queue"
```
