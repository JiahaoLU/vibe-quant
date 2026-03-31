# Strategy Performance Tracking Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Track per-strategy realized PnL using notional attribution, flowing through a new `StrategyBundleEvent` that carries both combined signals and per-strategy fractional weights.

**Architecture:** `StrategyContainer` emits a `StrategyBundleEvent` (replacing `SignalBundleEvent` in the queue) containing the already-aggregated `combined` signals plus a `per_strategy` attribution dict. `SimplePortfolio` fill logic is unchanged; `on_fill` uses the attribution fractions to apportion each fill's cash impact across strategies.

**Tech Stack:** Python 3.10+ stdlib only; pytest for tests.

---

### Task 1: Add `StrategyBundleEvent` to events, demote `SignalBundleEvent`

**Files:**
- Modify: `trading/events.py`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_events.py`, add at the bottom:

```python
from trading.events import StrategyBundleEvent

def test_strategy_bundle_event_type():
    ts = datetime(2020, 1, 2)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=0.8)
    e = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": sig},
        per_strategy={"strat_0": {"AAPL": 1.0}},
    )
    assert e.type == EventType.STRATEGY_BUNDLE

def test_signal_bundle_is_not_event_subclass():
    assert not issubclass(SignalBundleEvent, Event)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_events.py::test_strategy_bundle_event_type tests/test_events.py::test_signal_bundle_is_not_event_subclass -v
```

Expected: `FAILED` — `StrategyBundleEvent` not defined, `SignalBundleEvent` still subclasses `Event`.

- [ ] **Step 3: Update `trading/events.py`**

Replace the entire file with:

```python
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum, auto
from typing import Literal  # noqa: F401 — kept for OrderEvent/FillEvent


class EventType(Enum):
    BAR_BUNDLE      = auto()
    STRATEGY_BUNDLE = auto()
    ORDER           = auto()
    FILL            = auto()


@dataclass
class Event:
    type: EventType


@dataclass
class TickEvent:                 # value type — not an Event subclass, not queued directly
    symbol:       str
    timestamp:    datetime
    open:         float
    high:         float
    low:          float
    close:        float
    volume:       float
    is_synthetic: bool = False   # True when bar is carry-forwarded (no real data at this timestamp)


@dataclass
class BarBundleEvent(Event):
    timestamp:     datetime
    bars:          dict[str, TickEvent]   # symbol → tick
    is_end_of_day: bool = True
    type: EventType = field(default=EventType.BAR_BUNDLE, init=False)


@dataclass
class SignalEvent:               # value type — not an Event subclass, not queued directly
    symbol:    str
    timestamp: datetime
    signal:    float             # target weight in [-1, 1]; sum across bundle ≤ 1; >0 long, <0 short, =0 exit


@dataclass
class SignalBundleEvent:         # value type — not queued; used internally by strategies and StrategyContainer
    timestamp: datetime
    signals:   dict[str, SignalEvent]   # symbol → signal


@dataclass
class StrategyBundleEvent(Event):
    timestamp:    datetime
    combined:     dict[str, SignalEvent]        # aggregated signal per symbol (used by portfolio fill logic)
    per_strategy: dict[str, dict[str, float]]  # strategy_id → symbol → fractional weight (sums to 1.0 per symbol)
    type: EventType = field(default=EventType.STRATEGY_BUNDLE, init=False)


@dataclass
class OrderEvent(Event):
    symbol:          str
    timestamp:       datetime
    order_type:      Literal["MARKET", "LIMIT"]
    direction:       Literal["BUY", "SELL", "HOLD"]
    quantity:        int
    reference_price: float = 0.0  # fill reference price (next bar's open for EOD signals); execution handler applies slippage
    type: EventType = field(default=EventType.ORDER, init=False)


@dataclass
class FillEvent(Event):
    symbol:     str
    timestamp:  datetime
    direction:  Literal["BUY", "SELL", "HOLD"]
    quantity:   int
    fill_price: float
    commission: float
    type: EventType = field(default=EventType.FILL, init=False)
```

- [ ] **Step 4: Update the stale test in `tests/test_events.py`**

Remove `test_signal_bundle_event_type` (it checked `EventType.SIGNAL_BUNDLE` which no longer exists). Replace it with a test confirming `SignalBundleEvent` is a plain dataclass:

Find and replace in `tests/test_events.py`:

```python
# REMOVE this test:
def test_signal_bundle_event_type():
    sig = SignalEvent(symbol="AAPL", timestamp=datetime(2020, 1, 2), signal=1.0)
    e = SignalBundleEvent(timestamp=datetime(2020, 1, 2), signals={"AAPL": sig})
    assert e.type == EventType.SIGNAL_BUNDLE
```

Update the import at the top of `tests/test_events.py` — add `StrategyBundleEvent`, remove `SIGNAL_BUNDLE` from EventType assertions if present:

```python
from trading.events import (
    EventType, Event, BarBundleEvent, SignalEvent, SignalBundleEvent,
    StrategyBundleEvent, OrderEvent, FillEvent, TickEvent,
)
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_events.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add trading/events.py tests/test_events.py
git commit -m "feat: add StrategyBundleEvent; demote SignalBundleEvent to value type"
```

---

### Task 2: Add `name` field to `StrategyParams`

**Files:**
- Modify: `trading/base/strategy_params.py`

- [ ] **Step 1: Write the failing test**

In `tests/test_strategy_container.py`, add at the bottom:

```python
def test_strategy_params_name_defaults_to_empty():
    params = StrategyParams(symbols=["AAPL"])
    assert params.name == ""

def test_strategy_params_name_can_be_set():
    params = StrategyParams(symbols=["AAPL"], name="my_strategy")
    assert params.name == "my_strategy"
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_strategy_container.py::test_strategy_params_name_defaults_to_empty tests/test_strategy_container.py::test_strategy_params_name_can_be_set -v
```

Expected: `FAILED` — `StrategyParams` has no `name` field.

- [ ] **Step 3: Update `trading/base/strategy_params.py`**

```python
from dataclasses import dataclass, field


@dataclass
class StrategyParams:
    symbols: list[str]
    nominal: float = 1.0
    name:    str   = ""
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_strategy_container.py::test_strategy_params_name_defaults_to_empty tests/test_strategy_container.py::test_strategy_params_name_can_be_set -v
```

Expected: `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add trading/base/strategy_params.py tests/test_strategy_container.py
git commit -m "feat: add optional name field to StrategyParams"
```

---

### Task 3: Update `StrategyContainer` to emit `StrategyBundleEvent`

**Files:**
- Modify: `trading/impl/strategy_container.py`
- Modify: `tests/test_strategy_container.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_strategy_container.py`:

```python
from trading.events import StrategyBundleEvent

def test_container_emits_strategy_bundle_event():
    """Container emits StrategyBundleEvent (not SignalBundleEvent) after this change."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    assert isinstance(collected[0], StrategyBundleEvent)

def test_strategy_bundle_combined_matches_signal():
    """combined field on StrategyBundleEvent carries the aggregated signal."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert "AAPL" in collected[0].combined
    assert abs(collected[0].combined["AAPL"].signal - 1.0) < 1e-9

def test_per_strategy_single_strategy_is_100_percent():
    """Single strategy always gets 100% attribution for each symbol."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], name="alpha"))
    container.get_signals(_bundle(["AAPL"]))
    bundle = collected[0]
    assert abs(bundle.per_strategy["alpha"]["AAPL"] - 1.0) < 1e-9

def test_per_strategy_two_equal_nominal_strategies():
    """Two strategies with equal nominals each get 50% attribution."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=1.0, name="a"))
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=1.0, name="b"))
    container.get_signals(_bundle(["AAPL"]))
    ps = collected[0].per_strategy
    assert abs(ps["a"]["AAPL"] - 0.5) < 1e-9
    assert abs(ps["b"]["AAPL"] - 0.5) < 1e-9

def test_per_strategy_fractions_sum_to_one():
    """Attribution fractions across all strategies sum to 1.0 for each symbol."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=3.0, name="a"))
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=2.0, name="b"))
    container.get_signals(_bundle(["AAPL"]))
    ps = collected[0].per_strategy
    total = sum(ps[sid]["AAPL"] for sid in ps if "AAPL" in ps[sid])
    assert abs(total - 1.0) < 1e-9

def test_strategy_id_uses_name_when_provided():
    """Strategy ID in per_strategy uses StrategyParams.name when non-empty."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], name="my_strat"))
    container.get_signals(_bundle(["AAPL"]))
    assert "my_strat" in collected[0].per_strategy

def test_strategy_id_fallback_uses_classname_and_index():
    """When name is empty, strategy ID is ClassName_index."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert "_AlwaysLong_0" in collected[0].per_strategy

def test_full_exit_sell_attribution_distributed_to_previously_long():
    """When combined == 0 (full exit), attribution is split equally among strategies that were long."""

    class _ExitsOnSecondBar(Strategy):
        """Returns signal 1.0 on bar 1, then 0.0 on bar 2."""
        def _init(self, p): self._bar = 0
        def calculate_signals(self, event):
            self._bar += 1
            sig = 1.0 if self._bar == 1 else 0.0
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=sig)},
            )

    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_ExitsOnSecondBar, StrategyParams(symbols=["AAPL"], name="exiter"))
    container.get_signals(_bundle(["AAPL"]))   # bar 1: signal 1.0
    collected.clear()
    container.get_signals(_bundle(["AAPL"]))   # bar 2: signal 0.0 → full exit
    assert len(collected) == 1
    ps = collected[0].per_strategy
    assert "exiter" in ps
    assert abs(ps["exiter"]["AAPL"] - 1.0) < 1e-9
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_strategy_container.py::test_container_emits_strategy_bundle_event tests/test_strategy_container.py::test_per_strategy_single_strategy_is_100_percent tests/test_strategy_container.py::test_full_exit_sell_attribution_distributed_to_previously_long -v
```

Expected: `FAILED`.

- [ ] **Step 3: Update `trading/impl/strategy_container.py`**

```python
from typing import Callable

from trading.base.strategy_params import StrategyParams

from ..base.strategy import Strategy, StrategySignalGenerator
from ..events import BarBundleEvent, Event, SignalBundleEvent, StrategyBundleEvent, SignalEvent, TickEvent


class StrategyContainer(StrategySignalGenerator):
    """
    Holds multiple strategies, dispatches BarBundleEvents to each via calculate_signals,
    then aggregates their results into a single weighted StrategyBundleEvent.

    Each strategy's contribution is proportional to its nominal.  Signals are
    carried forward from the last bar on which a strategy fired, so a strategy
    that returns None this bar still contributes its previous target weights.
    One combined StrategyBundleEvent is emitted per bar whenever at least one
    strategy has fired at least once.

    Important: a strategy that has *never* fired (e.g. still warming up) has an
    empty carry-forward and therefore contributes zero signal, but its nominal is
    still included in total_nominal.  This means it dilutes all other strategies'
    effective weight until it fires for the first time.  Register strategies only
    when they are ready to produce signals, or accept this warm-up dilution.
    """

    def __init__(
        self,
        emit:     Callable[[Event], None],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(get_bars=get_bars)
        self._emit_fn    = emit
        self._strategies: list[tuple[Strategy, float]] = []   # (strategy, nominal)
        self._carried:    list[dict[str, float]]        = []   # parallel; symbol → last signal
        self._ids:        list[str]                     = []   # parallel; strategy id

    @property
    def symbols(self) -> list[str]:
        """Union of symbols across all contained strategies (order-preserving, deduplicated)."""
        seen: set[str] = set()
        result: list[str] = []
        for strategy, _ in self._strategies:
            for sym in getattr(strategy, "symbols", []):
                if sym not in seen:
                    seen.add(sym)
                    result.append(sym)
        return result

    def emit(self, event: Event) -> None:
        self._emit_fn(event)

    def add(
        self,
        strategy_class:  type[Strategy],
        strategy_params: StrategyParams,
        *,
        get_bars: Callable[[str, int], list[TickEvent]] | None = None,
    ) -> None:
        """Factory: construct a strategy and register it with its nominal."""
        index = len(self._strategies)
        strategy_id = strategy_params.name if strategy_params.name else f"{strategy_class.__name__}_{index}"
        instance = strategy_class(
            get_bars=get_bars if get_bars is not None else self._get_bars,
            strategy_params=strategy_params,
        )
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})
        self._ids.append(strategy_id)

    def add_strategy(self, strategy: Strategy, nominal: float = 1.0) -> None:
        """Add a pre-constructed strategy instance with an explicit nominal."""
        index = len(self._strategies)
        strategy_id = f"{strategy.__class__.__name__}_{index}"
        self._strategies.append((strategy, nominal))
        self._carried.append({})
        self._ids.append(strategy_id)

    def get_signals(self, event: BarBundleEvent) -> None:
        # Snapshot carries before updating — needed for full-exit attribution
        prev_carried = [{**c} for c in self._carried]

        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            result = strategy.calculate_signals(event)
            strategy.on_get_signal(result)
            if result is not None:
                any_new = True
                for symbol, sig in result.signals.items():
                    self._carried[i][symbol] = sig.signal

        if not any_new:
            return

        total_nominal = sum(n for _, n in self._strategies) or 1.0

        # Weighted sum across all carried signals
        combined: dict[str, float] = {}
        for i, (_, nominal) in enumerate(self._strategies):
            weight = nominal / total_nominal
            for symbol, signal_val in self._carried[i].items():
                combined[symbol] = combined.get(symbol, 0.0) + signal_val * weight

        if not combined:
            return

        # Compute per-strategy attribution fractions
        per_strategy: dict[str, dict[str, float]] = {}
        for symbol, combined_val in combined.items():
            if combined_val != 0.0:
                for i, (_, nominal) in enumerate(self._strategies):
                    weight_i = nominal / total_nominal
                    carried_val = self._carried[i].get(symbol, 0.0)
                    frac = weight_i * carried_val / combined_val
                    if frac != 0.0:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = frac
            else:
                # Full exit: split equally among strategies that were long last bar
                prev_long = [i for i in range(len(self._strategies))
                             if prev_carried[i].get(symbol, 0.0) != 0.0]
                if prev_long:
                    share = 1.0 / len(prev_long)
                    for i in prev_long:
                        per_strategy.setdefault(self._ids[i], {})[symbol] = share

        self.emit(StrategyBundleEvent(
            timestamp=event.timestamp,
            combined={
                symbol: SignalEvent(symbol=symbol, timestamp=event.timestamp, signal=val)
                for symbol, val in combined.items()
            },
            per_strategy=per_strategy,
        ))
```

- [ ] **Step 4: Update stale container tests**

In `tests/test_strategy_container.py`, update tests that check for `SignalBundleEvent` type in collected events:

```python
# test_add_factory_emits_one_combined_bundle — change isinstance check:
def test_add_factory_emits_one_combined_bundle():
    """Container aggregates strategy results and emits exactly one StrategyBundleEvent."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    assert isinstance(collected[0], StrategyBundleEvent)

# test_add_strategy_accepts_prebuilt_instance — change isinstance check:
def test_add_strategy_accepts_prebuilt_instance():
    """add_strategy registers a pre-constructed instance; its signals flow through the container."""
    container_emit = []
    strategy = _AlwaysLong(
        get_bars=lambda s, n: [],
        strategy_params=StrategyParams(symbols=["AAPL"]),
    )
    container = StrategyContainer(emit=container_emit.append, get_bars=lambda s, n: [])
    container.add_strategy(strategy)
    container.get_signals(_bundle(["AAPL"]))
    assert len(container_emit) == 1
    assert isinstance(container_emit[0], StrategyBundleEvent)

# test_get_signals_combines_independent_symbol_strategies — access .combined not .signals:
def test_get_signals_combines_independent_symbol_strategies():
    """Two strategies for different symbols produce one combined bundle covering both."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"]))
    container.add(_AlwaysLong, StrategyParams(symbols=["MSFT"]))
    container.get_signals(_bundle(["AAPL", "MSFT"]))
    assert len(collected) == 1
    bundle = collected[0]
    assert "AAPL" in bundle.combined
    assert "MSFT" in bundle.combined

# test_two_strategies_same_symbol_weighted_by_nominal — access .combined not .signals:
def test_two_strategies_same_symbol_weighted_by_nominal():
    """Two strategies targeting the same symbol emit one combined bundle with weighted signal."""
    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=3.0))
    container.add(_AlwaysLong, StrategyParams(symbols=["AAPL"], nominal=2.0))
    container.get_signals(_bundle(["AAPL"]))
    assert len(collected) == 1
    combined_signal = collected[0].combined["AAPL"].signal
    assert abs(combined_signal - 1.0) < 1e-9

# test_nominal_weights_combined_signal — access .combined not .signals:
def test_nominal_weights_combined_signal():
    """Strategy with double the nominal contributes proportionally more to the combined signal."""

    class _HalfSignal(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={s: SignalEvent(symbol=s, timestamp=ts, signal=0.5) for s in self.symbols},
            )

    class _FullSignal(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={s: SignalEvent(symbol=s, timestamp=ts, signal=1.0) for s in self.symbols},
            )

    collected = []
    container = StrategyContainer(emit=collected.append, get_bars=lambda s, n: [])
    container.add(_HalfSignal, StrategyParams(symbols=["AAPL"], nominal=1.0))
    container.add(_FullSignal, StrategyParams(symbols=["AAPL"], nominal=1.0))
    container.get_signals(_bundle(["AAPL"]))

    assert len(collected) == 1
    assert abs(collected[0].combined["AAPL"].signal - 0.75) < 1e-9

# test_on_get_signal_called_with_bundle_when_signals_fire — remove isinstance check on SignalBundleEvent:
def test_on_get_signal_called_with_bundle_when_signals_fire():
    """Container calls on_get_signal with the bundle when calculate_signals returns one."""
    hook_calls = []

    class _TrackHook(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            ts = event.timestamp
            return SignalBundleEvent(
                timestamp=ts,
                signals={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)},
            )
        def on_get_signal(self, result): hook_calls.append(result)

    container = StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])
    container.add(_TrackHook, StrategyParams(symbols=["AAPL"]))
    container.get_signals(_bundle(["AAPL"]))
    assert len(hook_calls) == 1
    assert isinstance(hook_calls[0], SignalBundleEvent)
```

Also update the import line at the top of `tests/test_strategy_container.py`:

```python
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent, StrategyBundleEvent, TickEvent
```

- [ ] **Step 5: Run all container tests**

```
pytest tests/test_strategy_container.py -v
```

Expected: all `PASSED`.

- [ ] **Step 6: Commit**

```bash
git add trading/impl/strategy_container.py tests/test_strategy_container.py
git commit -m "feat: StrategyContainer emits StrategyBundleEvent with per-strategy attribution"
```

---

### Task 4: Update `Portfolio` ABC and `SimplePortfolio` signal path

**Files:**
- Modify: `trading/base/portfolio.py`
- Modify: `trading/impl/simple_portfolio.py`
- Modify: `tests/test_portfolio.py`

- [ ] **Step 1: Update `trading/base/portfolio.py`**

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

    @property
    @abstractmethod
    def equity_curve(self) -> list[dict]: ...
```

- [ ] **Step 2: Update `SimplePortfolio` signal path**

In `trading/impl/simple_portfolio.py`:

1. Update the import line to use `StrategyBundleEvent` instead of `SignalBundleEvent`:

```python
from ..events import BarBundleEvent, Event, FillEvent, OrderEvent, StrategyBundleEvent, TickEvent
```

2. Update `__init__` — change `_pending_signals` type hint and add `_current_attribution`:

```python
def __init__(
    self,
    emit:            Callable[[Event], None],
    get_bars:        Callable[[str, int], list[TickEvent]],
    symbols:         list[str],
    initial_capital: float = 10_000.0,
):
    super().__init__(emit)
    self._get_bars            = get_bars
    self._symbols             = symbols
    self._cash                = initial_capital
    self._initial_capital     = initial_capital
    self._holdings: dict[str, int] = {s: 0 for s in symbols}
    self._equity_curve: list[dict] = []
    self._pending_signals: StrategyBundleEvent | None = None
    self._current_attribution: dict[str, dict[str, float]] = {}
```

3. Update `fill_pending_orders` — read `pending.combined` and save attribution:

```python
def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None:
    pending = self._pending_signals
    self._pending_signals = None
    self._current_attribution = pending.per_strategy if pending is not None else {}

    emitted_any = False
    available_cash = self._cash
    for symbol, signal_event in (pending.combined.items() if pending is not None else []):
        # No shorts: clamp negative signals to zero
        weight = max(0.0, signal_event.signal)
        bar = bar_bundle.bars.get(symbol)
        if bar is None:
            continue
        price = bar.open
        if price <= 0:
            continue

        target_qty  = int(weight * self._initial_capital / price)
        current_qty = self._holdings.get(symbol, 0)
        delta       = target_qty - current_qty

        if delta > 0 and available_cash >= delta * price:
            available_cash -= delta * price
            self._emit(OrderEvent(
                symbol          = symbol,
                timestamp       = bar_bundle.timestamp,
                order_type      = "MARKET",
                direction       = "BUY",
                quantity        = delta,
                reference_price = price,
            ))
            emitted_any = True
        elif delta < 0:
            self._emit(OrderEvent(
                symbol          = symbol,
                timestamp       = bar_bundle.timestamp,
                order_type      = "MARKET",
                direction       = "SELL",
                quantity        = abs(delta),
                reference_price = price,
            ))
            emitted_any = True

    if not emitted_any:
        self._emit(OrderEvent(
            symbol          = "",
            timestamp       = bar_bundle.timestamp,
            order_type      = "MARKET",
            direction       = "HOLD",
            quantity        = 0,
            reference_price = 0.0,
        ))
```

4. Update `on_signal` signature:

```python
def on_signal(self, event: StrategyBundleEvent) -> None:
    self._pending_signals = event
```

- [ ] **Step 3: Update existing portfolio tests to use `StrategyBundleEvent`**

In `tests/test_portfolio.py`, replace the import and helper:

```python
from trading.impl.simple_portfolio import SimplePortfolio
from trading.events import (
    BarBundleEvent, FillEvent, OrderEvent, StrategyBundleEvent, SignalEvent, TickEvent,
)


def _strategy_bundle(symbol: str, signal: float, ts=None, strategy_id: str = "test") -> StrategyBundleEvent:
    ts = ts or datetime(2020, 1, 2)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal=signal)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={symbol: sig},
        per_strategy={strategy_id: {symbol: 1.0}} if signal > 0 else {},
    )
```

Replace every call to `_signal_bundle(...)` with `_strategy_bundle(...)` throughout the file (same arguments, same behaviour).

Also update `test_multi_symbol_normalised_signals_do_not_overdraw_cash` which constructs a `SignalBundleEvent` directly — replace with `StrategyBundleEvent`:

```python
def test_multi_symbol_normalised_signals_do_not_overdraw_cash():
    """Equal-weight signals (0.5 each) for 2 symbols should fit within initial_capital."""
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={
            "AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=0.5),
            "MSFT": SignalEvent(symbol="MSFT", timestamp=ts, signal=0.5),
        },
        per_strategy={
            "test": {"AAPL": 1.0, "MSFT": 1.0},
        },
    )
    portfolio.on_signal(bundle)

    fill_ts = datetime(2020, 1, 3)
    fill_bar = BarBundleEvent(
        timestamp=fill_ts,
        bars={
            "AAPL": TickEvent(symbol="AAPL", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
            "MSFT": TickEvent(symbol="MSFT", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
        },
    )
    portfolio.fill_pending_orders(fill_bar)

    total_order_value = sum(o.quantity * o.reference_price for o in collected)
    assert total_order_value <= 10_000.0, f"Orders exceed cash: {total_order_value}"
```

- [ ] **Step 4: Run all portfolio tests**

```
pytest tests/test_portfolio.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add trading/base/portfolio.py trading/impl/simple_portfolio.py tests/test_portfolio.py
git commit -m "feat: update Portfolio ABC and SimplePortfolio to accept StrategyBundleEvent"
```

---

### Task 5: Add per-strategy PnL attribution to `SimplePortfolio`

**Files:**
- Modify: `trading/impl/simple_portfolio.py`
- Modify: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_portfolio.py`:

```python
def test_single_strategy_realized_pnl_equals_total_cash_impact():
    """With one strategy, realized_pnl tracks all fills at 100% attribution."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    # BUY 10 @ 100, commission 1.0 → cash impact = 10*100 + 1 = 1001 (cost)
    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 100, 100.0))   # 100 shares @ 100, comm 1.0

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]
    assert "s1" in pnl
    assert abs(pnl["s1"] - (-100 * 100.0 - 1.0)) < 1e-6   # -(cost + commission)


def test_single_strategy_buy_then_sell_profit():
    """Buy at 100, sell at 120 → realized PnL = 120*qty - 100*qty - 2*commission."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))    # cost: 10*100 + 1 = 1001

    portfolio.on_signal(_strategy_bundle("AAPL", 0.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 120.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 10, 120.0))   # revenue: 10*120 - 1 = 1199

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]
    assert abs(pnl - (10 * 120.0 - 1.0 - 10 * 100.0 - 1.0)) < 1e-6   # 198.0


def test_two_strategies_equal_nominal_split_commission():
    """Two equal-nominal strategies each absorb 50% of the commission."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)},
        per_strategy={"a": {"AAPL": 0.5}, "b": {"AAPL": 0.5}},
    )
    portfolio.on_signal(bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))   # commission = 1.0

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]
    # Each strategy absorbs 50% of cost: -(10*100 + 1) * 0.5 = -500.5
    assert abs(pnl["a"] - (-500.5)) < 1e-6
    assert abs(pnl["b"] - (-500.5)) < 1e-6


def test_full_exit_fill_pnl_not_zero():
    """After a full exit (combined==0), the SELL fill's PnL is still attributed (not silently dropped)."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    # Buy via a bundle where combined > 0
    ts = datetime(2020, 1, 2)
    buy_bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)},
        per_strategy={"s1": {"AAPL": 1.0}},
    )
    portfolio.on_signal(buy_bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))

    pnl_after_buy = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]

    # Sell via a bundle where combined == 0 — per_strategy has s1 with full exit attribution
    sell_bundle = StrategyBundleEvent(
        timestamp=datetime(2020, 1, 3),
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=datetime(2020, 1, 3), signal=0.0)},
        per_strategy={"s1": {"AAPL": 1.0}},   # full-exit attribution from container
    )
    portfolio.on_signal(sell_bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 120.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 10, 120.0))

    pnl_after_sell = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]
    assert pnl_after_sell > pnl_after_buy   # sell proceeds increased PnL


def test_hold_fill_does_not_change_strategy_pnl():
    """HOLD fills do not affect strategy_pnl."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))
    pnl_before = dict(portfolio.equity_curve[-1]["strategy_pnl"])

    from trading.events import FillEvent
    portfolio.on_fill(FillEvent(
        symbol="", timestamp=datetime(2020, 1, 3),
        direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
    ))
    pnl_after = portfolio.equity_curve[-1]["strategy_pnl"]
    assert pnl_after == pnl_before


def test_strategy_pnl_property_matches_equity_curve():
    """strategy_pnl property returns rows with timestamp + strategy columns."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))

    rows = portfolio.strategy_pnl
    assert len(rows) == 1
    assert "timestamp" in rows[0]
    assert "s1" in rows[0]
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_portfolio.py::test_single_strategy_realized_pnl_equals_total_cash_impact tests/test_portfolio.py::test_strategy_pnl_property_matches_equity_curve -v
```

Expected: `FAILED` — `_strategy_realized_pnl` not defined.

- [ ] **Step 3: Update `SimplePortfolio` with attribution tracking**

In `trading/impl/simple_portfolio.py`, add `_strategy_realized_pnl` to `__init__` (after `_current_attribution`):

```python
self._strategy_realized_pnl: dict[str, float] = {}
```

Update `on_fill` to apportion fills and include `strategy_pnl` in the equity snapshot:

```python
def on_fill(self, event: FillEvent) -> None:
    if event.direction != "HOLD":
        multiplier = 1 if event.direction == "BUY" else -1
        self._holdings[event.symbol] = self._holdings.get(event.symbol, 0) + multiplier * event.quantity
        self._cash -= multiplier * event.fill_price * event.quantity + event.commission

        # Apportion fill's cash impact across strategies
        fill_cash_impact = multiplier * event.fill_price * event.quantity + event.commission
        for strategy_id, symbol_weights in self._current_attribution.items():
            share = symbol_weights.get(event.symbol, 0.0)
            if share:
                self._strategy_realized_pnl[strategy_id] = (
                    self._strategy_realized_pnl.get(strategy_id, 0.0) - share * fill_cash_impact
                )

    market_value = 0.0
    for symbol in self._symbols:
        bars = self._get_bars(symbol, 1)
        if bars:
            market_value += self._holdings.get(symbol, 0) * bars[-1].close

    self._equity_curve.append({
        "timestamp":    event.timestamp,
        "cash":         self._cash,
        "holdings":     dict(self._holdings),
        "market_value": market_value,
        "equity":       self._cash + market_value,
        "strategy_pnl": dict(self._strategy_realized_pnl),
    })
```

Add `strategy_pnl` property after `equity_curve`:

```python
@property
def strategy_pnl(self) -> list[dict]:
    return [
        {"timestamp": row["timestamp"], **row["strategy_pnl"]}
        for row in self._equity_curve
    ]
```

- [ ] **Step 4: Run all portfolio tests**

```
pytest tests/test_portfolio.py -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add trading/impl/simple_portfolio.py tests/test_portfolio.py
git commit -m "feat: add per-strategy realized PnL attribution to SimplePortfolio"
```

---

### Task 6: Update `backtester.py` and its tests

**Files:**
- Modify: `trading/backtester.py`
- Modify: `tests/test_backtester.py`

- [ ] **Step 1: Update `trading/backtester.py`**

Replace both `SIGNAL_BUNDLE` cases (main loop and drain loop) with `STRATEGY_BUNDLE`:

```python
import queue

from .base.data      import DataHandler
from .base.execution import ExecutionHandler
from .base.portfolio import Portfolio
from .base.strategy  import StrategySignalGenerator
from .events         import EventType


class Backtester:
    def __init__(
        self,
        events:    queue.Queue,
        data:      DataHandler,
        strategy:  StrategySignalGenerator,
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
            while not self._events.empty():
                event = self._events.get(block=False)
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

            if not self._data.update_bars():
                break

        while not self._events.empty():
            event = self._events.get(block=False)
            match event.type:
                case EventType.BAR_BUNDLE:
                    self._strategy.get_signals(event)
                case EventType.STRATEGY_BUNDLE:
                    self._portfolio.on_signal(event)
                case EventType.ORDER:
                    self._execution.execute_order(event)
                case EventType.FILL:
                    self._portfolio.on_fill(event)
```

- [ ] **Step 2: Update `tests/test_backtester.py`**

Replace `test_signal_bundle_routes_to_portfolio` — it uses a `SignalBundleEvent` which is no longer enqueued. Replace with `StrategyBundleEvent`:

```python
from trading.events import (
    BarBundleEvent, FillEvent, OrderEvent, StrategyBundleEvent, SignalEvent, TickEvent,
)

def test_strategy_bundle_routes_to_portfolio():
    events = queue.Queue()
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()

    ts = datetime(2020, 1, 2)
    sig = SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": sig},
        per_strategy={"strat_0": {"AAPL": 1.0}},
    )
    events.put(bundle)

    bt = Backtester(events, _stopped_data(), strategy, portfolio, execution)
    bt.run()

    portfolio.on_signal.assert_called_once_with(bundle)
```

- [ ] **Step 3: Run all backtester tests**

```
pytest tests/test_backtester.py -v
```

Expected: all `PASSED`.

- [ ] **Step 4: Run the full test suite**

```
pytest -v
```

Expected: all `PASSED`.

- [ ] **Step 5: Commit**

```bash
git add trading/backtester.py tests/test_backtester.py
git commit -m "feat: route STRATEGY_BUNDLE in Backtester; update backtester tests"
```

---

### Task 7: Update `run_backtest.py` — export `strategy_pnl.csv` and print summary

**Files:**
- Modify: `run_backtest.py`

- [ ] **Step 1: Update `run_backtest.py`**

Replace the results-writing block (after `bt.run()`) with:

```python
curve = portfolio.equity_curve
if not curve:
    print("No trades were executed — strategy never triggered.")
else:
    final_equity = curve[-1]["equity"]
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    print(f"Initial capital : ${INITIAL_CAPITAL:>10,.2f}")
    print(f"Final equity    : ${final_equity:>10,.2f}")
    print(f"Total return    : {total_return:>+.2f}%")
    print(f"Trades (fills)  : {len(curve)}")

    # Per-strategy realized PnL summary
    final_pnl = curve[-1]["strategy_pnl"]
    if final_pnl:
        print("\nStrategy realized PnL:")
        for strategy_id, pnl in sorted(final_pnl.items()):
            print(f"  {strategy_id:<30} ${pnl:>+10,.2f}")

    with open(RESULTS_PATH, "w", newline="") as f:
        fieldnames = ["timestamp", "cash", "holdings", "market_value", "equity"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in curve:
            writer.writerow({
                "timestamp":    row["timestamp"],
                "cash":         row["cash"],
                "holdings":     str(row["holdings"]),
                "market_value": row["market_value"],
                "equity":       row["equity"],
            })
    print(f"Equity curve    : {RESULTS_PATH}")

    # Export per-strategy PnL CSV
    strategy_pnl_rows = portfolio.strategy_pnl
    if strategy_pnl_rows:
        strategy_ids = [k for k in strategy_pnl_rows[-1] if k != "timestamp"]
        pnl_path = RESULTS_PATH.replace("equity_curve.csv", "strategy_pnl.csv")
        with open(pnl_path, "w", newline="") as f:
            fieldnames = ["timestamp"] + strategy_ids
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in strategy_pnl_rows:
                writer.writerow(row)
        print(f"Strategy PnL    : {pnl_path}")
```

- [ ] **Step 2: Run the full backtest end-to-end**

```
python run_backtest.py
```

Expected output includes:
- `Initial capital`, `Final equity`, `Total return`, `Trades (fills)` lines
- `Strategy realized PnL:` section with at least one strategy listed
- `Equity curve    : results/equity_curve.csv`
- `Strategy PnL    : results/strategy_pnl.csv`

Verify `results/strategy_pnl.csv` exists and has a `timestamp` column plus one column per strategy.

- [ ] **Step 3: Commit**

```bash
git add run_backtest.py
git commit -m "feat: export strategy_pnl.csv and print per-strategy PnL summary"
```
