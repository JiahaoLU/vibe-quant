# Strategy / DataHandler Decoupling Design

**Date:** 2026-03-28

## Problem

`SMACrossoverStrategy.__init__` currently accepts a `DataHandler` instance and calls `self._data.get_latest_bars(symbol, n)` inside `calculate_signals`. This means a researcher implementing a custom strategy must understand the engine's `DataHandler` ABC — an internal infrastructure concern that has nothing to do with signal logic.

## Goal

A researcher should be able to implement a strategy knowing only:
- `BarBundleEvent` (the input to `calculate_signals`)
- `SignalBundleEvent` / `SignalEvent` (the output)
- `self.get_bars(symbol, n) -> list[TickEvent]` (available as a method on the class)

No imports from `trading.base.data`, no knowledge of queues, CSVs, or engine internals.

## Design

### Strategy ABC (`trading/base/strategy.py`)

The ABC gains an `__init__` that accepts a single callable and exposes it as a concrete `get_bars` method:

```python
class Strategy(ABC):
    def __init__(self, get_bars: Callable[[str, int], list[TickEvent]]):
        self._get_bars = get_bars

    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> None: ...
```

`get_bars` is wired at construction — there is no window between object creation and a usable `get_bars`.

### Concrete strategy (`trading/impl/strategy.py`)

The `DataHandler` parameter is replaced by the `get_bars` callable, passed to `super().__init__`:

```python
class SMACrossoverStrategy(Strategy):
    def __init__(self, events, symbols, get_bars, fast=10, slow=30):
        super().__init__(get_bars)
        self._events  = events
        self._symbols = symbols
        ...
```

`calculate_signals` is unchanged — it already calls `self._data.get_latest_bars`, which becomes `self.get_bars`.

### Engine wiring (`run_backtest.py`)

One-line change — pass the bound method instead of the object:

```python
# before
strategy = SMACrossoverStrategy(events, data, SYMBOLS)

# after
strategy = SMACrossoverStrategy(events, SYMBOLS, data.get_latest_bars)
```

The backtester is untouched. `DataHandler` and `Strategy` have no knowledge of each other; the engine is the only place that connects them.

### Researcher experience

A researcher implementing a custom strategy needs no engine imports:

```python
from trading.base.strategy import Strategy
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent

class MyStrategy(Strategy):
    def __init__(self, events, symbols, get_bars):
        super().__init__(get_bars)
        self._events  = events
        self._symbols = symbols

    def calculate_signals(self, event: BarBundleEvent) -> None:
        bars = self.get_bars("AAPL", 30)
        # ... compute signal ...
```

Testing requires no mocks — a plain lambda suffices:

```python
strategy = MyStrategy(events, ["AAPL"], get_bars=lambda s, n: fake_bars)
```

## Files Changed

| File | Change |
|---|---|
| `trading/base/strategy.py` | Add `__init__` accepting `get_bars` callable; add concrete `get_bars` method |
| `trading/base/data.py` | Update `get_latest_bars` return type annotation to `list[TickEvent]` |
| `trading/impl/strategy.py` | Replace `data: DataHandler` param with `get_bars` callable; call `super().__init__(get_bars)`; replace `self._data.get_latest_bars` with `self.get_bars` |
| `run_backtest.py` | Pass `data.get_latest_bars` instead of `data` to strategy constructor |
| `tests/test_strategy.py` | Replace `MagicMock` DataHandler with a plain lambda |

## What Does Not Change

- `BarBundleEvent`, `SignalBundleEvent`, `SignalEvent`, `TickEvent` — unchanged
- `Backtester` event loop — unchanged
- `Portfolio`, `ExecutionHandler` — unchanged
- `DataHandler` ABC — unchanged (only return type annotation update)
