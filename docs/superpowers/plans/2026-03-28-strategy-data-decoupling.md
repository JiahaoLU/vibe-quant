# Strategy / DataHandler Decoupling Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Decouple `Strategy` from `DataHandler` so a researcher can implement a strategy without knowing anything about the engine's data infrastructure.

**Architecture:** The `Strategy` ABC gains an `__init__` that accepts a `get_bars` callable and exposes it as `self.get_bars(symbol, n)`. The concrete `SMACrossoverStrategy` drops its `DataHandler` parameter and calls `super().__init__(get_bars)`. The engine wires the two by passing `data.get_latest_bars` at construction time.

**Tech Stack:** Python 3.10+ stdlib only. `pytest` for tests.

---

### Task 1: Update the Strategy ABC

**Files:**
- Modify: `trading/base/strategy.py`
- Modify: `tests/test_strategy.py` (existing tests must still pass after this task)

- [ ] **Step 1: Write a failing test for the new ABC contract**

Add to `tests/test_strategy.py`:

```python
from trading.base.strategy import Strategy
from trading.events import BarBundleEvent, TickEvent
from datetime import datetime

def test_strategy_abc_exposes_get_bars():
    """get_bars on the ABC should delegate to the callable passed at construction."""
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> None:
            pass

    stub = _Stub(get_bars=lambda s, n: [tick])
    result = stub.get_bars("AAPL", 1)
    assert result == [tick]
```

- [ ] **Step 2: Run the test to confirm it fails**

```bash
source .venv/bin/activate
pytest tests/test_strategy.py::test_strategy_abc_exposes_get_bars -v
```

Expected: `FAIL` — `TypeError: Strategy.__init__` does not exist yet.

- [ ] **Step 3: Update the Strategy ABC**

Replace the entire contents of `trading/base/strategy.py` with:

```python
from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, TickEvent


class Strategy(ABC):
    def __init__(self, get_bars: Callable[[str, int], list[TickEvent]]):
        self._get_bars = get_bars

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> None:
        """Consume a BarBundleEvent and emit a SignalBundleEvent if conditions are met."""
        ...
```

- [ ] **Step 4: Run the new test to confirm it passes**

```bash
pytest tests/test_strategy.py::test_strategy_abc_exposes_get_bars -v
```

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add trading/base/strategy.py tests/test_strategy.py
git commit -m "feat: Strategy ABC accepts get_bars callable, exposes self.get_bars"
```

---

### Task 2: Update SMACrossoverStrategy

**Files:**
- Modify: `trading/impl/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Update the existing test helpers to use a lambda instead of a MagicMock**

The existing `_bundle` and `_bars` helpers are fine. The only change is in how the strategy is constructed in every test — replace the `MagicMock` data object with a `get_bars` lambda.

Replace the two helper functions and all strategy constructors in `tests/test_strategy.py`:

```python
import queue
from datetime import datetime
from trading.impl.strategy import SMACrossoverStrategy
from trading.events import BarBundleEvent, SignalBundleEvent, TickEvent


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
    from trading.base.strategy import Strategy
    ts = datetime(2020, 1, 2)
    tick = TickEvent(symbol="AAPL", timestamp=ts, open=1.0, high=1.0, low=1.0, close=1.0, volume=1.0)

    class _Stub(Strategy):
        def calculate_signals(self, event: BarBundleEvent) -> None:
            pass

    stub = _Stub(get_bars=lambda s, n: [tick])
    assert stub.get_bars("AAPL", 1) == [tick]


def test_no_signal_before_enough_history():
    events = queue.Queue()
    bars = _bars([100.0] * 5)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))
    assert events.empty()


def test_long_signal_when_fast_above_slow():
    events = queue.Queue()
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert not events.empty()
    bundle = events.get_nowait()
    assert isinstance(bundle, SignalBundleEvent)
    assert bundle.signals["AAPL"].signal_type == "LONG"


def test_no_duplicate_long_signal():
    events = queue.Queue()
    bars = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    events.get_nowait()
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    assert events.empty()


def test_exit_signal_when_fast_below_slow():
    events = queue.Queue()
    bars_long = _bars([90.0] * 20 + [110.0] * 10)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars_long, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"], close=110.0))
    events.get_nowait()

    bars_exit = _bars([110.0] * 20 + [90.0] * 10)
    strategy._get_bars = lambda s, n: bars_exit
    strategy.calculate_signals(_bundle(["AAPL"], close=90.0))
    bundle = events.get_nowait()
    assert bundle.signals["AAPL"].signal_type == "EXIT"


def test_no_signal_when_flat():
    events = queue.Queue()
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL"]))
    assert events.empty()


def test_multi_symbol_signals_are_independent():
    events = queue.Queue()
    def get_bars(symbol, n):
        if symbol == "AAPL":
            return _bars([90.0] * 20 + [110.0] * 10)
        return _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL", "MSFT"], get_bars=get_bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    bundle = events.get_nowait()
    assert "AAPL" in bundle.signals
    assert "MSFT" not in bundle.signals


def test_no_emission_when_no_symbol_signals():
    events = queue.Queue()
    bars = _bars([100.0] * 30)
    strategy = SMACrossoverStrategy(events, ["AAPL", "MSFT"], get_bars=lambda s, n: bars, fast=10, slow=30)
    strategy.calculate_signals(_bundle(["AAPL", "MSFT"]))
    assert events.empty()
```

- [ ] **Step 2: Run the tests to confirm they fail**

```bash
pytest tests/test_strategy.py -v
```

Expected: most tests `FAIL` — `SMACrossoverStrategy` still expects `data` as second positional arg.

- [ ] **Step 3: Update SMACrossoverStrategy**

Replace the entire contents of `trading/impl/strategy.py` with:

```python
import queue
from typing import Callable

from ..base.strategy import Strategy
from ..events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


class SMACrossoverStrategy(Strategy):
    """
    Emits LONG when the fast SMA crosses above the slow SMA for a symbol.
    Emits EXIT when the fast SMA crosses below the slow SMA.
    Operates on multiple symbols simultaneously.
    """

    def __init__(
        self,
        events:   queue.Queue,
        symbols:  list[str],
        get_bars: Callable[[str, int], list[TickEvent]],
        fast:     int = 10,
        slow:     int = 30,
    ):
        super().__init__(get_bars)
        self._events   = events
        self._symbols  = symbols
        self._fast     = fast
        self._slow     = slow
        self._position: dict[str, str | None] = {s: None for s in symbols}

    def calculate_signals(self, event: BarBundleEvent) -> None:
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

        if signals:
            self._events.put(SignalBundleEvent(
                timestamp = event.timestamp,
                signals   = signals,
            ))
```

- [ ] **Step 4: Run all strategy tests to confirm they pass**

```bash
pytest tests/test_strategy.py -v
```

Expected: all `PASS`

- [ ] **Step 5: Commit**

```bash
git add trading/impl/strategy.py tests/test_strategy.py
git commit -m "feat: SMACrossoverStrategy decoupled from DataHandler"
```

---

### Task 3: Update engine wiring and type annotation

**Files:**
- Modify: `run_backtest.py`
- Modify: `trading/base/data.py`

- [ ] **Step 1: Fix the return type annotation on DataHandler**

Replace the contents of `trading/base/data.py` with:

```python
from abc import ABC, abstractmethod

from ..events import TickEvent


class DataHandler(ABC):
    @abstractmethod
    def update_bars(self) -> bool:
        """Emit the next bar bundle as a BarBundleEvent. Returns False when data is exhausted."""
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        """Return the last N bars for a symbol."""
        ...
```

- [ ] **Step 2: Update run_backtest.py wiring**

Change line 28 in `run_backtest.py` from:

```python
strategy  = SMACrossoverStrategy(events, data, SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW)
```

to:

```python
strategy  = SMACrossoverStrategy(events, SYMBOLS, data.get_latest_bars, fast=FAST_WINDOW, slow=SLOW_WINDOW)
```

- [ ] **Step 3: Run the full test suite**

```bash
pytest tests/ -v
```

Expected: all 34 tests `PASS`

- [ ] **Step 4: Run the backtest end-to-end**

```bash
python run_backtest.py
```

Expected output (values may vary slightly):
```
Initial capital : $ 10,000.00
Final equity    : $  7,834.38
Total return    : -21.66%
Trades (fills)  : 28
Equity curve    : results/equity_curve.csv
```

- [ ] **Step 5: Commit**

```bash
git add trading/base/data.py run_backtest.py
git commit -m "feat: wire strategy via get_bars callable, update DataHandler type annotation"
```

---

### Task 4: Update CLAUDE.md strategy guide

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update the "Adding a new strategy" section**

In `CLAUDE.md`, replace the existing "Adding a new strategy" section with:

```markdown
## Adding a new strategy

1. Create `trading/impl/my_strategy.py`; subclass `Strategy` from `trading.base.strategy`
2. Implement `calculate_signals(self, event: BarBundleEvent) -> None`
3. Accept `events: queue.Queue`, `symbols: list[str]`, and `get_bars: Callable[[str, int], list[TickEvent]]` in the constructor; call `super().__init__(get_bars)`
4. Call `self.get_bars(symbol, n)` to retrieve bar history — no DataHandler import needed
5. Emit signals via `self._events.put(SignalBundleEvent(...))` — only when at least one symbol has a signal
6. Export it from `trading/impl/__init__.py`
7. Wire it in `run_backtest.py`: pass `data.get_latest_bars` as the `get_bars` argument
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update strategy guide for get_bars decoupling"
```
