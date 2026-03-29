# StrategyContainer Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Introduce `StrategyBase` ABC and `StrategyContainer` so multiple independent strategies can be run together without changing the `Backtester` interface.

**Architecture:** Split the current `Strategy` ABC into `StrategyBase` (shared wiring: `__init__`, abstract `get_signals`) and `Strategy` (adds `get_bars()` helper and `calculate_signals`). `StrategyContainer` extends `StrategyBase`, holds a list of strategies, and dispatches `get_signals` to each. The `Backtester` type hint changes from `Strategy` to `StrategyBase` — everything else is untouched.

**Tech Stack:** Python 3.10+ stdlib only. `pytest` for tests.

---

### Task 1: Add StrategyBase ABC

**Files:**
- Modify: `trading/base/strategy.py`
- Modify: `tests/test_strategy.py`

- [ ] **Step 1: Write two failing tests**

Add these tests to the end of `tests/test_strategy.py`:

```python
def test_strategy_is_subclass_of_strategy_base():
    from trading.base.strategy import StrategyBase
    assert issubclass(Strategy, StrategyBase)


def test_strategy_base_get_signals_is_abstract():
    from trading.base.strategy import StrategyBase

    class _NoImpl(StrategyBase):
        pass

    try:
        _NoImpl(emit=lambda e: None, get_bars=lambda s, n: [])
        assert False, "Expected TypeError"
    except TypeError:
        pass
```

- [ ] **Step 2: Run to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py::test_strategy_is_subclass_of_strategy_base tests/test_strategy.py::test_strategy_base_get_signals_is_abstract -v
```

Expected: `FAIL` — `ImportError: cannot import name 'StrategyBase'`.

- [ ] **Step 3: Replace trading/base/strategy.py**

```python
from abc import ABC, abstractmethod
from typing import Callable

from ..events import BarBundleEvent, Event, SignalBundleEvent, TickEvent


class StrategyBase(ABC):
    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        self._emit     = emit
        self._get_bars = get_bars

    @abstractmethod
    def get_signals(self, event: BarBundleEvent) -> None:
        """Process a bar bundle. May emit zero or more SignalBundleEvents."""
        ...


class Strategy(StrategyBase):
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
source .venv/bin/activate && pytest tests/test_strategy.py::test_strategy_is_subclass_of_strategy_base tests/test_strategy.py::test_strategy_base_get_signals_is_abstract -v
```

Expected: both `PASS`.

- [ ] **Step 5: Run the full strategy test suite**

```bash
source .venv/bin/activate && pytest tests/test_strategy.py -v
```

Expected: all 12 `PASS` — existing tests are unaffected since `Strategy`'s interface is unchanged.

- [ ] **Step 6: Commit**

```bash
git add trading/base/strategy.py tests/test_strategy.py
git commit -m "feat: extract StrategyBase ABC from Strategy"
```

---

### Task 2: Implement StrategyContainer

**Files:**
- Create: `trading/impl/strategy_container.py`
- Create: `tests/test_strategy_container.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_strategy_container.py`:

```python
from datetime import datetime
from trading.base.strategy import Strategy, StrategyBase
from trading.impl.strategy_container import StrategyContainer
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, TickEvent


def _bundle(symbols: list[str], close: float = 100.0) -> BarBundleEvent:
    ts = datetime(2020, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={s: TickEvent(symbol=s, timestamp=ts, open=close, high=close, low=close, close=close, volume=1000.0)
              for s in symbols},
    )


class _AlwaysLong(Strategy):
    """Stub that always returns a LONG signal for every symbol."""
    def __init__(self, emit, symbols, get_bars):
        super().__init__(emit, get_bars)
        self._symbols = symbols

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        ts = event.timestamp
        signals = {s: SignalEvent(symbol=s, timestamp=ts, signal_type="LONG") for s in self._symbols}
        return SignalBundleEvent(timestamp=ts, signals=signals)


class _NeverSignals(Strategy):
    """Stub that always returns None."""
    def __init__(self, emit, get_bars):
        super().__init__(emit, get_bars)

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        return None


def test_container_is_subclass_of_strategy_base():
    assert issubclass(StrategyContainer, StrategyBase)


def test_add_factory_injects_default_emit_and_get_bars():
    """Factory add injects container's emit and get_bars when not in kwargs."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    assert isinstance(collected[0], SignalBundleEvent)


def test_add_factory_respects_overridden_emit():
    """Factory add uses a custom emit kwarg, not the container default."""
    default_collected = []
    custom_collected = []
    container = StrategyContainer(emit=default_collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"], emit=custom_collected.append)
    container.get_signals(_bundle(["AAPL"]))
    assert len(custom_collected) == 1
    assert default_collected == []


def test_add_factory_respects_overridden_get_bars():
    """Factory add uses a custom get_bars kwarg, not the container default."""
    default_calls = []
    custom_calls = []
    container = StrategyContainer(
        emit=lambda e: None,
        get_bars=lambda s, n: default_calls.append(s) or [],
    )
    container.add(_AlwaysLong, symbols=["AAPL"], get_bars=lambda s, n: custom_calls.append(s) or [])
    container.get_signals(_bundle(["AAPL"]))
    assert "AAPL" in custom_calls
    assert default_calls == []


def test_add_strategy_accepts_prebuilt_instance():
    """add_strategy adds a pre-constructed instance and dispatches to it."""
    collected = []
    strategy = _AlwaysLong(emit=collected.append, symbols=["AAPL"], get_bars=lambda s, n: [])
    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])
    container.add_strategy(strategy)
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1


def test_get_signals_dispatches_to_all_strategies():
    """All contained strategies receive the bar bundle."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.add(_AlwaysLong, symbols=["MSFT"])
    container.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 2


def test_strategy_returning_none_emits_nothing():
    """A strategy returning None from calculate_signals does not emit."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_NeverSignals)
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_empty_container_emits_nothing():
    """An empty container does not crash and emits nothing."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.get_signals(_bundle(["AAPL"]))
    assert collected == []


def test_two_strategies_same_symbol_emit_independent_bundles():
    """Two strategies for the same symbol emit two separate SignalBundleEvents."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.add(_AlwaysLong, symbols=["AAPL"])
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 2
    assert all(isinstance(e, SignalBundleEvent) for e in collected)
```

- [ ] **Step 2: Run to confirm they fail**

```bash
source .venv/bin/activate && pytest tests/test_strategy_container.py -v
```

Expected: `FAIL` — `ModuleNotFoundError: No module named 'trading.impl.strategy_container'`.

- [ ] **Step 3: Create trading/impl/strategy_container.py**

```python
from typing import Callable

from ..base.strategy import StrategyBase
from ..events import BarBundleEvent, Event, TickEvent


class StrategyContainer(StrategyBase):
    """
    Holds multiple strategies and dispatches BarBundleEvents to each.
    Each contained strategy emits its own SignalBundleEvent independently.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(emit, get_bars)
        self._strategies: list[StrategyBase] = []

    def add(self, strategy_class: type[StrategyBase], /, **kwargs) -> None:
        """Factory: construct a strategy, injecting emit and get_bars as defaults."""
        kwargs.setdefault("emit", self._emit)
        kwargs.setdefault("get_bars", self._get_bars)
        self._strategies.append(strategy_class(**kwargs))

    def add_strategy(self, strategy: StrategyBase) -> None:
        """Add a pre-constructed strategy instance."""
        self._strategies.append(strategy)

    def get_signals(self, event: BarBundleEvent) -> None:
        for strategy in self._strategies:
            strategy.get_signals(event)
```

- [ ] **Step 4: Run all container tests**

```bash
source .venv/bin/activate && pytest tests/test_strategy_container.py -v
```

Expected: all 9 `PASS`.

- [ ] **Step 5: Run the full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests `PASS`.

- [ ] **Step 6: Commit**

```bash
git add trading/impl/strategy_container.py tests/test_strategy_container.py
git commit -m "feat: add StrategyContainer — distributes BarBundleEvents to multiple strategies"
```

---

### Task 3: Wire everything together

**Files:**
- Modify: `trading/impl/__init__.py`
- Modify: `trading/backtester.py`
- Modify: `run_backtest.py`

- [ ] **Step 1: Export StrategyContainer from trading/impl/__init__.py**

Replace the entire file:

```python
from .data               import MultiCSVDataHandler
from .execution          import SimulatedExecutionHandler
from .portfolio          import SimplePortfolio
from .strategy           import SMACrossoverStrategy
from .strategy_container import StrategyContainer

__all__ = [
    "MultiCSVDataHandler",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "SMACrossoverStrategy",
    "StrategyContainer",
]
```

- [ ] **Step 2: Update the Backtester type hint**

In `trading/backtester.py`, change the import and type hint for `strategy`:

```python
import queue

from .base.data      import DataHandler
from .base.execution import ExecutionHandler
from .base.portfolio import Portfolio
from .base.strategy  import StrategyBase
from .events         import EventType


class Backtester:
    def __init__(
        self,
        events:    queue.Queue,
        data:      DataHandler,
        strategy:  StrategyBase,
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

- [ ] **Step 3: Update run_backtest.py**

Replace the strategy wiring section. The full updated wiring block (lines 26–32):

```python
events    = queue.Queue()
data      = MultiCSVDataHandler(events.put, SYMBOLS, CSV_PATHS)
strategy  = StrategyContainer(events.put, data.get_latest_bars)
strategy.add(SMACrossoverStrategy, symbols=SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, SYMBOLS, initial_capital=INITIAL_CAPITAL)
execution = SimulatedExecutionHandler(events.put, commission=COMMISSION, slippage_pct=SLIPPAGE_PCT)

bt = Backtester(events, data, strategy, portfolio, execution)
```

Also update the import at the top of `run_backtest.py` to include `StrategyContainer`:

```python
from trading.impl.strategy  import SMACrossoverStrategy
from trading.impl.strategy_container import StrategyContainer
```

Or more simply, since `StrategyContainer` is now exported from `trading.impl`:

```python
from trading.impl import (
    MultiCSVDataHandler,
    SimulatedExecutionHandler,
    SimplePortfolio,
    SMACrossoverStrategy,
    StrategyContainer,
)
```

- [ ] **Step 4: Run the full test suite**

```bash
source .venv/bin/activate && pytest tests/ -v
```

Expected: all tests `PASS`.

- [ ] **Step 5: Run the backtest end-to-end**

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

- [ ] **Step 6: Commit**

```bash
git add trading/impl/__init__.py trading/backtester.py run_backtest.py
git commit -m "feat: wire StrategyContainer into Backtester and run_backtest.py"
```

---

### Task 4: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture rules and strategy guide**

In `CLAUDE.md`, make these two changes:

**1. Update the ABCs rule** (replace the existing bullet):

```markdown
- **ABCs are load-bearing.** `DataHandler`, `StrategyBase`, `Strategy`, `Portfolio`, `ExecutionHandler` are abstract base classes in `trading/base/`. `StrategyBase` defines the shared wiring; `Strategy` adds the researcher-facing `calculate_signals` interface. Concrete implementations live in `trading/impl/`.
```

**2. Replace the entire "Adding a new strategy" section:**

```markdown
## Adding a new strategy

1. Create `trading/impl/my_strategy.py`; subclass `Strategy` from `trading.base.strategy`
2. Implement `calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None` — return a `SignalBundleEvent` when signals fire, `None` otherwise
3. Accept `symbols: list[str]` (and any other strategy-specific params) in the constructor; call `super().__init__(emit, get_bars)` — `emit` and `get_bars` are injected by `StrategyContainer` automatically
4. Call `self.get_bars(symbol, n)` to retrieve bar history — no DataHandler import needed
5. Do **not** call `self._emit()` directly — return the bundle from `calculate_signals`; `get_signals` (inherited from `Strategy`) handles emission
6. Export it from `trading/impl/__init__.py`
7. Register it in `run_backtest.py`:

   ```python
   strategy = StrategyContainer(events.put, data.get_latest_bars)
   strategy.add(MyStrategy, symbols=SYMBOLS)
   ```
```

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for StrategyBase hierarchy and StrategyContainer wiring"
```
