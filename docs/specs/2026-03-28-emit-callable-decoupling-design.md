# Emit Callable Decoupling Design

**Date:** 2026-03-28

## Problem

All four components (`Strategy`, `Portfolio`, `ExecutionHandler`, `DataHandler`) currently accept a `queue.Queue` instance and call `self._events.put(...)` to emit events. This couples every component to the concrete `queue.Queue` type and its API, making components harder to test in isolation and harder to reason about independently.

## Goal

Replace `events: queue.Queue` with `emit: Callable[[Event], None]` across all components. Each component only needs to call a function — it has no knowledge of queues, threading, or how events are routed.

For `Strategy` specifically, go one step further: `calculate_signals` becomes a pure computation method that returns a `SignalBundleEvent | None`. A new `get_signals` method on the ABC wraps the call and handles the emit. The researcher implementing a strategy never sees or calls `emit` directly.

## Design

### Strategy ABC (`trading/base/strategy.py`)

`__init__` accepts both `emit` and `get_bars`. A new concrete `get_signals` method wraps `calculate_signals` and emits the result. `calculate_signals` changes its return type from `None` to `SignalBundleEvent | None`.

```python
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

### Other ABCs (`portfolio.py`, `execution.py`, `data.py`)

Each gains `__init__(emit)`:

```python
class Portfolio(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

class ExecutionHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit

class DataHandler(ABC):
    def __init__(self, emit: Callable[[Event], None]):
        self._emit = emit
```

### Concrete implementations

Each concrete class calls `super().__init__(emit)` (or `super().__init__(emit, get_bars)` for Strategy) and replaces every `self._events.put(X)` with `self._emit(X)`.

`SMACrossoverStrategy.calculate_signals` changes from emitting directly to returning the `SignalBundleEvent`:

```python
def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
    signals = {}
    # ... compute signals ...
    return SignalBundleEvent(timestamp=event.timestamp, signals=signals) if signals else None
```

### Backtester (`trading/backtester.py`)

One line change — call `get_signals` instead of `calculate_signals`:

```python
# before
strategy.calculate_signals(event)

# after
strategy.get_signals(event)
```

### Engine wiring (`run_backtest.py`)

Pass `events.put` to all constructors:

```python
events    = queue.Queue()
data      = MultiCSVDataHandler(events.put, SYMBOLS, CSV_PATHS)
strategy  = SMACrossoverStrategy(events.put, SYMBOLS, data.get_latest_bars, ...)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, SYMBOLS, ...)
execution = SimulatedExecutionHandler(events.put, ...)
```

### Researcher experience

The researcher implements `calculate_signals` as a pure function. No `emit`, no queue, no infrastructure:

```python
class MyStrategy(Strategy):
    def __init__(self, symbols, emit, get_bars):
        super().__init__(emit, get_bars)
        self._symbols = symbols

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        bars = self.get_bars("AAPL", 30)
        # ... compute ...
        return SignalBundleEvent(...) if signals else None
```

Testing requires no mocks:

```python
collected = []
strategy = MyStrategy(["AAPL"], emit=collected.append, get_bars=lambda s, n: fake_bars)
strategy.get_signals(bundle)
assert collected[0].signals["AAPL"].signal_type == "LONG"
```

## Files Changed

| File | Change |
|---|---|
| `trading/base/strategy.py` | `__init__(emit, get_bars)`; add `get_signals`; `calculate_signals` returns `SignalBundleEvent \| None` |
| `trading/base/portfolio.py` | Add `__init__(emit)` |
| `trading/base/execution.py` | Add `__init__(emit)` |
| `trading/base/data.py` | Add `__init__(emit)` |
| `trading/impl/strategy.py` | `super().__init__(emit, get_bars)`; `calculate_signals` returns instead of emitting |
| `trading/impl/portfolio.py` | `super().__init__(emit)`; `self._emit(...)` replaces `self._events.put(...)` |
| `trading/impl/execution.py` | `super().__init__(emit)`; `self._emit(...)` replaces `self._events.put(...)` |
| `trading/impl/data.py` | `super().__init__(emit)`; `self._emit(...)` replaces `self._events.put(...)` |
| `trading/backtester.py` | `strategy.get_signals(event)` instead of `strategy.calculate_signals(event)` |
| `run_backtest.py` | Pass `events.put` to all constructors |
| `tests/test_strategy.py` | Pass `emit` callable; test via `get_signals`; assert on returned/emitted values |
| `tests/test_portfolio.py` | Pass `emit` callable instead of queue |
| `tests/test_backtester.py` | Pass `emit` callable instead of queue |
| `tests/test_data.py` | Pass `emit` callable instead of queue |
| `tests/test_events.py` | No change needed |

## What Does Not Change

- All event dataclasses (`BarBundleEvent`, `SignalBundleEvent`, etc.) — unchanged
- `Backtester` owns the queue — only the dispatch call changes
- `Portfolio` and `ExecutionHandler` internal logic — only constructor and emit calls change
