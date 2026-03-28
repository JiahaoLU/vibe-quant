# StrategyContainer Design

**Date:** 2026-03-28

## Problem

The engine currently supports exactly one strategy. A researcher who wants to run multiple independent strategies must combine their logic manually into a single class, mixing concerns that should be separate.

## Goal

Introduce a `StrategyContainer` that holds multiple strategies, distributes `BarBundleEvent` to each, and lets each emit its own `SignalBundleEvent` independently. A shared context (`emit`, `get_bars`) is maintained by the container so factory-created strategies need not receive those as explicit arguments.

## Class Hierarchy

```
StrategyBase (ABC)            trading/base/strategy.py
├── Strategy (ABC)            trading/base/strategy.py
└── StrategyContainer         trading/impl/strategy_container.py
```

### `StrategyBase` ABC

New ABC, placed above `Strategy` in `trading/base/strategy.py`. Contains only what both subclasses share:

```python
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
```

`self._get_bars` is stored but no `get_bars()` helper method is exposed — that lives only on `Strategy`.

### `Strategy` ABC

Unchanged in behaviour. Now extends `StrategyBase` and adds:
- `get_bars(symbol, n)` — concrete helper wrapping `self._get_bars`
- concrete `get_signals(event)` — calls `calculate_signals`, emits result if not `None`
- abstract `calculate_signals(event) -> SignalBundleEvent | None`

```python
class Strategy(StrategyBase):
    def get_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        return self._get_bars(symbol, n)

    def get_signals(self, event: BarBundleEvent) -> None:
        result = self.calculate_signals(event)
        if result is not None:
            self._emit(result)

    @abstractmethod
    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        ...
```

Existing concrete strategies (`SMACrossoverStrategy`) require no changes.

### `StrategyContainer`

Concrete class in `trading/impl/strategy_container.py`. Extends `StrategyBase`.

```python
class StrategyContainer(StrategyBase):
    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(emit, get_bars)
        self._strategies: list[StrategyBase] = []

    def add(self, strategy_class: type[StrategyBase], /, **kwargs) -> None:
        """Factory: construct a strategy with emit/get_bars injected as defaults."""
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

`get_bars()` is intentionally absent — `self._get_bars` is used only for factory injection, not for the container's own use.

## Data Flow

```
BarBundleEvent
    → StrategyContainer.get_signals(event)
        → strategy_A.get_signals(event)  →  emit(SignalBundleEvent_A)
        → strategy_B.get_signals(event)  →  emit(SignalBundleEvent_B)  [if signals fire]
        → strategy_C.get_signals(event)  →  (nothing)
```

Each strategy emits independently to the shared queue. The container never emits directly.

## Backtester

One-line type hint change: `strategy: Strategy` → `strategy: StrategyBase`. No logic changes.

## Engine Wiring (`run_backtest.py`)

```python
container = StrategyContainer(events.put, data.get_latest_bars)
container.add(SMACrossoverStrategy, symbols=SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW)

bt = Backtester(events, data, container, portfolio, execution)
```

A single strategy still works unchanged, since `SMACrossoverStrategy` (via `Strategy`) still satisfies the `StrategyBase` type.

## Testing

`tests/test_strategy_container.py` — no mocks, no queues:

```python
collected = []
container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: bars)
container.add(SMACrossoverStrategy, symbols=["AAPL"], fast=10, slow=30)
container.get_signals(bundle)
assert isinstance(collected[0], SignalBundleEvent)
```

Key test cases:
- `add()` factory injects default emit and get_bars
- `add()` factory respects overridden emit or get_bars in kwargs
- `add_strategy()` adds a pre-built instance
- `get_signals` dispatches to all contained strategies
- Strategies that return `None` from `calculate_signals` emit nothing
- Multiple strategies emit independent `SignalBundleEvent`s

## Files Changed

| File | Change |
|---|---|
| `trading/base/strategy.py` | Add `StrategyBase` ABC; `Strategy` extends it; `get_bars()` stays on `Strategy` |
| `trading/impl/strategy_container.py` | New — `StrategyContainer` |
| `trading/impl/__init__.py` | Export `StrategyContainer` |
| `trading/backtester.py` | `strategy: Strategy` → `strategy: StrategyBase`; update import |
| `run_backtest.py` | Replace single strategy with container |
| `tests/test_strategy_container.py` | New test file |

## What Does Not Change

- `SMACrossoverStrategy` — no changes
- All other ABCs (`Portfolio`, `ExecutionHandler`, `DataHandler`) — no changes
- All existing tests — no changes
- Event dataclasses — no changes
