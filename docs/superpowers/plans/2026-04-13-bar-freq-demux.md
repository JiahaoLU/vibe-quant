# Bar-Freq Demux Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow strategies in a `StrategyContainer` to declare their own `bar_freq`, so the data handler runs at the finest required frequency and the container demultiplexes bars to each strategy at its own cadence.

**Architecture:** `StrategyParams` gains a `bar_freq: str` field (same `"1d"` / `"Xm"` convention as `AlpacaDataHandler`). `StrategyContainer` exposes a `required_freq` property (the finest frequency across all registered strategies) and gates each strategy's `calculate_signals` call using a bar counter: strategy `i` fires only when `bar_count % steps[i] == 0`, where `steps[i] = strategy_freq_minutes / required_freq_minutes`. `required_freq` is promoted to an abstract property on `StrategySignalGenerator`. `DataHandler` ABC gains a `bar_freq` constructor param (default `"1d"`) exposed as a property; all three concrete handlers thread it through. Both wiring points (`run_live.py`, `run_backtest.py`) pass `bar_freq=strategy.required_freq` to their data handler at construction — alignment is the wiring point's responsibility, not the Backtester's.

**Tech Stack:** Pure Python stdlib — no new dependencies.

---

## File Map

| File | Action | What changes |
|---|---|---|
| `trading/base/strategy_params.py` | Modify | Add `bar_freq: str = "1d"` field |
| `trading/impl/strategy_signal_generator/strategy_container.py` | Modify | `_bar_freq_to_minutes()` helper, `required_freq` property, `_recompute_steps()`, demux counter in `get_signals()` |
| `run_live.py` | Modify | Derive `bar_freq` from `strategy.required_freq` |
| `run_backtest.py` | Modify | Pass `bar_freq=strategy.required_freq` to data handler |
| `trading/base/data.py` | Modify | Add `bar_freq` constructor param + property |
| `trading/impl/data_handler/alpaca_data_handler.py` | Modify | Pass `bar_freq` to `super().__init__`; remove duplicate private assignment |
| `trading/impl/data_handler/yahoo_data_handler.py` | Modify | Pass `bar_freq` to `super().__init__` |
| `trading/impl/data_handler/multi_csv_data_handler.py` | Modify | Pass `bar_freq` to `super().__init__` |
| `trading/base/strategy.py` | Modify | Add abstract `required_freq` property to `StrategySignalGenerator` |
| `tests/test_strategy_container_bar_freq.py` | Create | All new tests for demux behaviour |
| `tests/test_data_handler_bar_freq.py` | Create | Tests for `bar_freq` property on data handlers |

---

### Task 1: Add `bar_freq` to `StrategyParams`

**Files:**
- Modify: `trading/base/strategy_params.py`
- Test: `tests/test_strategy_container_bar_freq.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_strategy_container_bar_freq.py
from trading.base.strategy_params import StrategyParams


def test_strategy_params_bar_freq_defaults_to_1d():
    p = StrategyParams(symbols=["AAPL"], name="test")
    assert p.bar_freq == "1d"


def test_strategy_params_bar_freq_can_be_set():
    p = StrategyParams(symbols=["AAPL"], name="test", bar_freq="5m")
    assert p.bar_freq == "5m"
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_strategy_container_bar_freq.py -v
```
Expected: `TypeError` — `StrategyParams.__init__() got an unexpected keyword argument 'bar_freq'`

- [ ] **Step 3: Add the field**

```python
# trading/base/strategy_params.py
from dataclasses import dataclass


@dataclass
class StrategyParams:
    symbols:  list[str]
    name:     str
    nominal:  float = 1.0
    bar_freq: str   = "1d"
```

- [ ] **Step 4: Run to verify it passes**

```bash
pytest tests/test_strategy_container_bar_freq.py::test_strategy_params_bar_freq_defaults_to_1d \
       tests/test_strategy_container_bar_freq.py::test_strategy_params_bar_freq_can_be_set -v
```
Expected: PASS (2 tests)

- [ ] **Step 5: Verify existing tests unaffected**

```bash
pytest tests/ -v --tb=short
```
Expected: all previously passing tests still pass (no regressions; default `"1d"` is backward-compatible).

- [ ] **Step 6: Commit**

```bash
git add trading/base/strategy_params.py tests/test_strategy_container_bar_freq.py
git commit -m "feat: add bar_freq field to StrategyParams (default '1d')"
```

---

### Task 2: Add `required_freq` property to `StrategyContainer`

**Files:**
- Modify: `trading/impl/strategy_signal_generator/strategy_container.py`
- Test: `tests/test_strategy_container_bar_freq.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strategy_container_bar_freq.py`:

```python
from trading.base.strategy import Strategy
from trading.base.strategy_params import StrategyParams
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent
from trading.impl.strategy_signal_generator.strategy_container import StrategyContainer


class _Stub(Strategy):
    def _init(self, p): pass
    def calculate_signals(self, event): return None


def _make_container():
    return StrategyContainer(emit=lambda e: None, get_bars=lambda s, n: [])


def test_required_freq_returns_1d_when_no_strategies():
    container = _make_container()
    assert container.required_freq == "1d"


def test_required_freq_returns_1d_when_all_strategies_are_daily():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="1d"))
    assert container.required_freq == "1d"


def test_required_freq_returns_finest_intraday_freq():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="5m"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="1m"))
    assert container.required_freq == "1m"


def test_required_freq_raises_when_mixing_daily_and_intraday():
    import pytest
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    with pytest.raises(ValueError, match="Cannot mix"):
        _ = container.required_freq
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_strategy_container_bar_freq.py -k "required_freq" -v
```
Expected: `AttributeError: 'StrategyContainer' object has no attribute 'required_freq'`

- [ ] **Step 3: Add the helper function and `required_freq` property**

In `trading/impl/strategy_signal_generator/strategy_container.py`, add the module-level helper immediately after the imports block, and the property to `StrategyContainer`:

```python
# --- module-level helper (add after imports) ---

def _bar_freq_to_minutes(bar_freq: str) -> int:
    """Convert a bar_freq string to its minute equivalent.

    "1d" → 390  (6.5-hour trading day)
    "Xm" → X    (e.g. "5m" → 5)
    """
    if bar_freq == "1d":
        return 390
    return int(bar_freq.rstrip("m"))
```

In `StrategyContainer`, add this property (after the `symbols` property):

```python
@property
def required_freq(self) -> str:
    """The finest bar_freq declared across all registered strategies.

    Raises ValueError if daily ("1d") and intraday ("Xm") strategies are mixed,
    since the demux step count (390 / X) is ambiguous for arbitrary minute freqs.
    Returns "1d" when no strategies are registered.
    """
    if not self._strategies:
        return "1d"
    freqs = [s.strategy_params.bar_freq for s, _ in self._strategies]
    kinds = {"daily" if f == "1d" else "intraday" for f in freqs}
    if len(kinds) > 1:
        raise ValueError(
            "Cannot mix daily ('1d') and intraday ('Xm') strategies in the same "
            "StrategyContainer. Use separate containers or a single frequency."
        )
    if "daily" in kinds:
        return "1d"
    minutes = [_bar_freq_to_minutes(f) for f in freqs]
    return f"{min(minutes)}m"
```

- [ ] **Step 4: Run to verify they pass**

```bash
pytest tests/test_strategy_container_bar_freq.py -k "required_freq" -v
```
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add trading/impl/strategy_signal_generator/strategy_container.py \
        tests/test_strategy_container_bar_freq.py
git commit -m "feat: add required_freq property to StrategyContainer"
```

---

### Task 3: Add demux counter — gate `calculate_signals` by bar_freq

**Files:**
- Modify: `trading/impl/strategy_signal_generator/strategy_container.py`
- Test: `tests/test_strategy_container_bar_freq.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_strategy_container_bar_freq.py`:

```python
from datetime import datetime
from trading.events import BarBundleEvent, TickEvent


def _bundle(symbols: list[str]) -> BarBundleEvent:
    ts = datetime(2024, 1, 2)
    return BarBundleEvent(
        timestamp=ts,
        bars={
            s: TickEvent(symbol=s, timestamp=ts,
                         open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
            for s in symbols
        },
    )


def test_same_freq_strategy_fired_on_every_bar():
    """A '1m' strategy in a '1m' container fires on every bar."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(event.timestamp)
            return None

    container = _make_container()
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="s", bar_freq="1m"))
    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 5


def test_coarser_strategy_skipped_until_N_bars_elapsed():
    """A '5m' strategy in a '1m' container fires only once every 5 bars."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(event.timestamp)
            return None

    container = _make_container()
    # Register the 1m strategy first so required_freq resolves to "1m"
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="base", bar_freq="1m"))
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))
    for _ in range(10):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 2   # fires on bar 5 and bar 10


def test_coarser_strategy_carry_forward_used_between_fires():
    """Between fires, the coarser strategy's last signal is carried forward."""
    emitted = []

    class _LongOnFire(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            return SignalBundleEvent(
                timestamp=event.timestamp,
                signals={"AAPL": SignalEvent(symbol="AAPL", timestamp=event.timestamp, signal=1.0)},
            )

    container = StrategyContainer(emit=emitted.append, get_bars=lambda s, n: [])
    # Add a 1m base so required_freq="1m"; 5m fires every 5 bars
    container.add(_Stub,      StrategyParams(symbols=["AAPL"], name="base",  bar_freq="1m"))
    container.add(_LongOnFire, StrategyParams(symbols=["AAPL"], name="slow", bar_freq="5m"))

    # After 5 bars the 5m strategy fires and emits a StrategyBundleEvent
    for _ in range(5):
        container.get_signals(_bundle(["AAPL"]))
    assert len(emitted) == 1

    # Bar 6-9: carry-forward keeps the signal active even though _LongOnFire is not called
    for _ in range(4):
        container.get_signals(_bundle(["AAPL"]))
    # No new bundle emitted (no *new* signal from the 5m strategy between fires)
    assert len(emitted) == 1


def test_daily_strategies_fire_on_every_bar():
    """All '1d' strategies (the default) fire on every bar — no behaviour change."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(1)
            return None

    container = _make_container()
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="d", bar_freq="1d"))
    for _ in range(3):
        container.get_signals(_bundle(["AAPL"]))
    assert len(calls) == 3
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_strategy_container_bar_freq.py -k "coarser or same_freq or daily_strategies" -v
```
Expected: FAIL — coarser strategy tests fire on every bar (no demux yet).

- [ ] **Step 3: Add `_bar_count`, `_steps`, and `_recompute_steps()` to `StrategyContainer.__init__` and `add()`/`add_strategy()`**

In `__init__`, add two new instance variables after `self._ids`:

```python
self._bar_count: int       = 0
self._steps:     list[int] = []
```

Add the `_recompute_steps` method to `StrategyContainer`:

```python
def _recompute_steps(self) -> None:
    """Recompute the per-strategy bar step counts based on required_freq."""
    if not self._strategies:
        self._steps = []
        return
    req_minutes = _bar_freq_to_minutes(self.required_freq)
    self._steps = [
        _bar_freq_to_minutes(s.strategy_params.bar_freq) // req_minutes
        for s, _ in self._strategies
    ]
```

At the end of both `add()` and `add_strategy()`, call `self._recompute_steps()`:

In `add()` — after the three `append` calls:
```python
        self._strategies.append((instance, strategy_params.nominal))
        self._carried.append({})
        self._ids.append(strategy_id)
        self._recompute_steps()   # <-- add this line
```

In `add_strategy()` — after the three `append` calls:
```python
        self._strategies.append((strategy, nominal))
        self._carried.append({})
        self._ids.append(f"{strategy.__class__.__name__}_{len(self._strategies) - 1}")
        self._recompute_steps()   # <-- add this line
```

- [ ] **Step 4: Gate `calculate_signals` in `get_signals()`**

Replace the loop in `get_signals()` with the demux-aware version:

Old loop (lines ~83–93):
```python
        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            result = strategy.calculate_signals(event)
            strategy.on_get_signal(result)
            if result is not None:
                any_new = True
                for symbol, sig in result.signals.items():
                    self._carried[i][symbol] = sig.signal
```

New loop — increment the counter first, then gate each strategy:
```python
        self._bar_count += 1
        any_new = False
        for i, (strategy, _) in enumerate(self._strategies):
            steps = self._steps[i] if self._steps else 1
            if self._bar_count % steps != 0:
                continue   # carry-forward unchanged; strategy not called this bar
            result = strategy.calculate_signals(event)
            strategy.on_get_signal(result)
            if result is not None:
                any_new = True
                for symbol, sig in result.signals.items():
                    self._carried[i][symbol] = sig.signal
```

- [ ] **Step 5: Run new tests**

```bash
pytest tests/test_strategy_container_bar_freq.py -k "coarser or same_freq or daily_strategies" -v
```
Expected: PASS (4 tests)

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass. Pay particular attention to `tests/test_strategy_container.py` — the `on_get_signal_called_even_when_calculate_signals_returns_none` test should still pass (single strategy, steps=1, fires every bar).

- [ ] **Step 7: Commit**

```bash
git add trading/impl/strategy_signal_generator/strategy_container.py \
        tests/test_strategy_container_bar_freq.py
git commit -m "feat: demux bar_freq in StrategyContainer — gate calculate_signals by per-strategy step count"
```

---

### Task 4: Wire `required_freq` into both wiring points

**Files:**
- Modify: `run_live.py`
- Modify: `run_backtest.py`

- [ ] **Step 1: Update `run_live.py` — remove hard-coded `BAR_FREQ`**

In `run_live.py`, remove:
```python
BAR_FREQ           = "1d"               # "1d" for daily, "5m" for 5-minute intraday
```

Change the `AlpacaDataHandler` construction to use `strategy.required_freq`:
```python
data = AlpacaDataHandler(
    emit     = events.put,
    symbols  = symbols,
    bar_freq = strategy.required_freq,
    api_key  = API_KEY,
    secret   = SECRET,
)
```

- [ ] **Step 2: Update `run_backtest.py` — pass `bar_freq` to `YahooDataHandler`**

In `run_backtest.py`, change the `YahooDataHandler` construction:

Old:
```python
data = YahooDataHandler(
    events.put,
    symbols,
    start=START,
    end=END,
    fetch=fetch_daily_bars,
    universe_builder=universe_builder,
)
```

New:
```python
data = YahooDataHandler(
    events.put,
    symbols,
    start=START,
    end=END,
    fetch=fetch_daily_bars,
    universe_builder=universe_builder,
    bar_freq=strategy.required_freq,
)
```

- [ ] **Step 3: Verify both files parse without error**

```bash
python -c "import run_backtest" 2>&1 | head -5
python -c "import run_live"    2>&1 | head -5
```
Expected: either silent or env-var errors only — no `SyntaxError` or `AttributeError`.

- [ ] **Step 4: Run full test suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass.

- [ ] **Step 5: Commit**

```bash
git add run_live.py run_backtest.py
git commit -m "feat: derive bar_freq from strategy.required_freq in run_live and run_backtest"
```

---

### Task 5: Add `bar_freq` to `DataHandler` ABC and thread through all concrete handlers

**Files:**
- Modify: `trading/base/data.py`
- Modify: `trading/impl/data_handler/alpaca_data_handler.py`
- Modify: `trading/impl/data_handler/yahoo_data_handler.py`
- Modify: `trading/impl/data_handler/multi_csv_data_handler.py`
- Test: `tests/test_data_handler_bar_freq.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/test_data_handler_bar_freq.py
from unittest.mock import MagicMock


def test_alpaca_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    handler = AlpacaDataHandler(
        emit=MagicMock(), symbols=["AAPL"], bar_freq="5m",
        api_key="k", secret="s",
    )
    assert handler.bar_freq == "5m"


def test_yahoo_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.yahoo_data_handler import YahooDataHandler
    handler = YahooDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-10",
        fetch=lambda syms, s, e: {"AAPL": []},
        bar_freq="1d",
    )
    assert handler.bar_freq == "1d"


def test_multi_csv_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.multi_csv_data_handler import MultiCSVDataHandler
    handler = MultiCSVDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-05",
        bar_freq="5m",
    )
    assert handler.bar_freq == "5m"


def test_data_handler_default_bar_freq_is_1d():
    from trading.base.data import DataHandler

    class _MinimalHandler(DataHandler):
        def prefill(self): pass
        def update_bars(self): return False
        def get_latest_bars(self, symbol, n=1): return []

    handler = _MinimalHandler(emit=MagicMock())   # no bar_freq → defaults to "1d"
    assert handler.bar_freq == "1d"
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_data_handler_bar_freq.py -v
```
Expected: `AttributeError` on `bar_freq` for all handlers.

- [ ] **Step 3: Add `bar_freq` param and property to `DataHandler` ABC**

Replace `DataHandler.__init__` in `trading/base/data.py`:

```python
class DataHandler(ABC):
    def __init__(self, emit: Callable[[Event], None], bar_freq: str = "1d"):
        self._emit     = emit
        self._bar_freq = bar_freq

    @property
    def bar_freq(self) -> str:
        return self._bar_freq

    @abstractmethod
    def prefill(self) -> None:
        ...

    @abstractmethod
    def update_bars(self) -> bool:
        ...

    @abstractmethod
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        ...

    async def update_bars_async(self) -> bool:
        return await asyncio.to_thread(self.update_bars)
```

- [ ] **Step 4: Thread through `AlpacaDataHandler`**

In `trading/impl/data_handler/alpaca_data_handler.py`, update `__init__`:

Old:
```python
        super().__init__(emit)
        self._symbols        = symbols
        self._bar_freq       = bar_freq
```

New:
```python
        super().__init__(emit, bar_freq=bar_freq)
        self._symbols        = symbols
```

All existing uses of `self._bar_freq` (`prefill`, `update_bars_async`, `_seconds_until_next_bar`) continue to work because `super().__init__` sets it.

- [ ] **Step 5: Thread through `YahooDataHandler`**

In `trading/impl/data_handler/yahoo_data_handler.py`, add `bar_freq` to `__init__` and pass to super:

Old signature + super call:
```python
    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        start:       str,
        end:         str,
        fetch:       Callable[[list[str], str, str], dict[str, list[dict]]],
        max_history: int = 200,
        universe_builder: UniverseBuilder | None = None,
    ):
        super().__init__(emit)
```

New:
```python
    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        start:       str,
        end:         str,
        fetch:       Callable[[list[str], str, str], dict[str, list[dict]]],
        max_history: int = 200,
        universe_builder: UniverseBuilder | None = None,
        bar_freq:    str = "1d",
    ):
        super().__init__(emit, bar_freq=bar_freq)
```

- [ ] **Step 6: Thread through `MultiCSVDataHandler`**

In `trading/impl/data_handler/multi_csv_data_handler.py`, add `bar_freq` to `__init__` and pass to super:

Old signature + super call:
```python
    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        csv_paths:   list[str] | None = None,
        start:       str | None = None,
        end:         str | None = None,
        max_history: int = 200,
        date_format: str = "%Y-%m-%d",
        universe_builder: UniverseBuilder | None = None,
    ):
        ...
        super().__init__(emit)
```

New signature (add `bar_freq` before the guard block) and super call:
```python
    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        csv_paths:   list[str] | None = None,
        start:       str | None = None,
        end:         str | None = None,
        max_history: int = 200,
        date_format: str = "%Y-%m-%d",
        universe_builder: UniverseBuilder | None = None,
        bar_freq:    str = "1d",
    ):
        ...
        super().__init__(emit, bar_freq=bar_freq)
```

- [ ] **Step 7: Run to verify all tests pass**

```bash
pytest tests/test_data_handler_bar_freq.py -v
```
Expected: PASS (4 tests)

- [ ] **Step 8: Full suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass; `tests/test_alpaca_data_handler.py` must stay green.

- [ ] **Step 9: Commit**

```bash
git add trading/base/data.py \
        trading/impl/data_handler/alpaca_data_handler.py \
        trading/impl/data_handler/yahoo_data_handler.py \
        trading/impl/data_handler/multi_csv_data_handler.py \
        tests/test_data_handler_bar_freq.py
git commit -m "feat: add bar_freq property to DataHandler ABC; thread through all three concrete handlers"
```

---

### Task 6: Add abstract `required_freq` to `StrategySignalGenerator`

**Files:**
- Modify: `trading/base/strategy.py`

- [ ] **Step 1: Add the abstract property**

In `trading/base/strategy.py`, add `required_freq` as an abstract property to `StrategySignalGenerator` (after the `symbols` property in `StrategyBase`, but the declaration belongs on `StrategySignalGenerator` since only signal-emitting containers need it):

```python
class StrategySignalGenerator(StrategyBase):
    """ABC for components that receive bar bundles and emit signal bundles."""

    @property
    @abstractmethod
    def required_freq(self) -> str:
        """The finest bar_freq needed across all contained strategies."""
        ...

    @abstractmethod
    def emit(self, event: Event) -> None:
        ...

    @abstractmethod
    def get_signals(self, event: BarBundleEvent) -> None:
        ...
```

- [ ] **Step 2: Run the full suite**

```bash
pytest tests/ -v --tb=short
```
Expected: all tests pass. `StrategyContainer.required_freq` (added in Task 2) already satisfies the abstract requirement — no concrete class becomes abstract-incomplete.

- [ ] **Step 3: Commit**

```bash
git add trading/base/strategy.py
git commit -m "feat: promote required_freq to abstract property on StrategySignalGenerator"
```

---

## Self-Review

**Spec coverage:**
- `StrategyParams.bar_freq` → Task 1 ✓
- `StrategyContainer.required_freq` (finest freq) → Task 2 ✓
- Demux gating in `get_signals` → Task 3 ✓
- `run_live.py` wiring → Task 4 ✓
- `run_backtest.py` wiring → Task 4 ✓
- `DataHandler.bar_freq` property → Task 5 ✓
- All three concrete handlers thread `bar_freq` to ABC → Task 5 ✓
- `required_freq` abstract on `StrategySignalGenerator` → Task 6 ✓
- Mixing daily + intraday raises `ValueError` → Task 2, `required_freq` property ✓
- Backward compatibility (all `"1d"` strategies, default `bar_freq`) → Task 1 default + Task 3 `steps=1` path ✓

**Placeholder scan:** None found.

**Type consistency:**
- `_bar_freq_to_minutes` referenced in Task 2 (definition) and Task 3 (`_recompute_steps`) — consistent.
- `_steps` added to `__init__` in Task 3 and written by `_recompute_steps` called from `add()`/`add_strategy()` — consistent.
- `required_freq` defined concretely in Task 2, declared abstract in Task 6, consumed in Task 4 — consistent.
- `bar_freq` added to `DataHandler.__init__` in Task 5; `AlpacaDataHandler` removes its own `self._bar_freq` assignment and lets `super().__init__` set it — `self._bar_freq` continues to work in `prefill`, `update_bars_async`, `_seconds_until_next_bar` unchanged.
- `YahooDataHandler` and `MultiCSVDataHandler` add `bar_freq` as a trailing keyword-only param (default `"1d"`) — backward-compatible; no existing call sites need updating.
