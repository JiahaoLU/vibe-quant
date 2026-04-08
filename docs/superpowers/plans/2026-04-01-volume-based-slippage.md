# Volume-Based Slippage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the fixed-percentage slippage model with a volume-scaled square-root market impact model (Almgren et al.) that realistically penalizes large orders relative to daily volume, adds a dynamic spread floor, and guards against division-by-zero on synthetic bars.

**Architecture:** `OrderEvent` gains five optional bar-data fields (`bar_volume`, `bar_high`, `bar_low`, `bar_close`, `bar_is_synthetic`); `SimplePortfolio.fill_pending_orders` populates those fields from the fill bar; `SimulatedExecutionHandler` reads them to compute spread floor + volume impact at fill time. No new component types or event types are required.

**Tech Stack:** Python 3.10+, stdlib `math`, pytest

---

## File Map

| Action | File | Responsibility |
|--------|------|----------------|
| Modify | `trading/events.py` | Add bar-data fields to `OrderEvent` |
| Modify | `trading/impl/simple_portfolio.py` | Populate new fields when emitting BUY/SELL `OrderEvent`s |
| Modify | `trading/impl/simulated_execution_handler.py` | Add `market_impact_eta`; implement Tier 1 (volume impact), Tier 2 (spread floor), Tier 4 (synthetic guard) |
| Modify | `run_backtest.py` | Add `MARKET_IMPACT_ETA` constant; wire into `SimulatedExecutionHandler` |
| Create | `tests/test_simulated_execution_handler.py` | Unit tests for all new slippage behaviour |
| Modify | `tests/test_portfolio.py` | Assert new bar fields are populated on emitted orders |

---

## Task 1: Extend `OrderEvent` with bar data fields

**Files:**
- Modify: `trading/events.py`
- Test: `tests/test_events.py`

- [ ] **Step 1: Write the failing test**

Add to the bottom of `tests/test_events.py`:

```python
def test_order_event_carries_bar_data_fields():
    from datetime import datetime
    from trading.events import OrderEvent
    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
        reference_price=100.0,
        bar_volume=50_000.0, bar_high=101.0, bar_low=99.0,
        bar_close=100.5, bar_is_synthetic=False,
    )
    assert order.bar_volume == 50_000.0
    assert order.bar_high == 101.0
    assert order.bar_low == 99.0
    assert order.bar_close == 100.5
    assert order.bar_is_synthetic is False


def test_order_event_bar_fields_default_to_zero():
    from datetime import datetime
    from trading.events import OrderEvent
    order = OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="BUY", quantity=10,
        reference_price=100.0,
    )
    assert order.bar_volume == 0.0
    assert order.bar_high == 0.0
    assert order.bar_low == 0.0
    assert order.bar_close == 0.0
    assert order.bar_is_synthetic is False
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_events.py::test_order_event_carries_bar_data_fields tests/test_events.py::test_order_event_bar_fields_default_to_zero -v
```

Expected: FAIL — `TypeError: __init__() got an unexpected keyword argument 'bar_volume'`

- [ ] **Step 3: Implement — add fields to `OrderEvent` in `trading/events.py`**

In `trading/events.py`, replace the `OrderEvent` dataclass with:

```python
@dataclass
class OrderEvent(Event):
    symbol:          str
    timestamp:       datetime
    order_type:      Literal["MARKET", "LIMIT"]
    direction:       Literal["BUY", "SELL", "HOLD"]
    quantity:        int
    reference_price: float = 0.0   # fill reference price (next bar's open for EOD signals); execution handler applies slippage
    bar_volume:      float = 0.0   # day's total volume (0.0 when unknown)
    bar_high:        float = 0.0   # bar high; used for spread floor
    bar_low:         float = 0.0   # bar low; used for spread floor
    bar_close:       float = 0.0   # bar close; used for Parkinson vol normalisation
    bar_is_synthetic: bool = False  # True when the bar is carry-forwarded; skip volume impact
    type: EventType = field(default=EventType.ORDER, init=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_events.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add trading/events.py tests/test_events.py
git commit -m "feat: add bar data fields to OrderEvent for volume-based slippage"
```

---

## Task 2: Portfolio populates bar data fields in `OrderEvent`

**Files:**
- Modify: `trading/impl/simple_portfolio.py`
- Test: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing tests**

Add to the bottom of `tests/test_portfolio.py`:

```python
def test_fill_pending_orders_populates_bar_fields_on_buy():
    """BUY OrderEvent carries bar's volume/high/low/close/is_synthetic."""
    from datetime import datetime
    from trading.events import TickEvent, BarBundleEvent, StrategyBundleEvent, SignalEvent

    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    ts_signal = datetime(2020, 1, 2)
    portfolio.on_signal(StrategyBundleEvent(
        timestamp=ts_signal,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts_signal, signal=1.0)},
        per_strategy={"s": {"AAPL": 1.0}},
    ))

    ts_fill = datetime(2020, 1, 3)
    bar = TickEvent(symbol="AAPL", timestamp=ts_fill,
                    open=102.0, high=105.0, low=98.0, close=103.0,
                    volume=12_000.0, is_synthetic=False)
    portfolio.fill_pending_orders(BarBundleEvent(timestamp=ts_fill, bars={"AAPL": bar}))

    order = collected[0]
    assert order.direction == "BUY"
    assert order.bar_volume == 12_000.0
    assert order.bar_high == 105.0
    assert order.bar_low == 98.0
    assert order.bar_close == 103.0
    assert order.bar_is_synthetic is False


def test_fill_pending_orders_populates_bar_fields_on_sell():
    """SELL OrderEvent carries bar's volume/high/low/close/is_synthetic."""
    from datetime import datetime
    from trading.events import FillEvent, TickEvent, BarBundleEvent, StrategyBundleEvent, SignalEvent

    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 1),
        direction="BUY", quantity=50, fill_price=100.0, commission=0.0,
    ))

    ts_signal = datetime(2020, 1, 2)
    portfolio.on_signal(StrategyBundleEvent(
        timestamp=ts_signal,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts_signal, signal=0.0)},
        per_strategy={"s": {"AAPL": 1.0}},
    ))

    ts_fill = datetime(2020, 1, 3)
    bar = TickEvent(symbol="AAPL", timestamp=ts_fill,
                    open=110.0, high=112.0, low=108.0, close=111.0,
                    volume=8_000.0, is_synthetic=True)
    portfolio.fill_pending_orders(BarBundleEvent(timestamp=ts_fill, bars={"AAPL": bar}))

    order = collected[0]
    assert order.direction == "SELL"
    assert order.bar_volume == 8_000.0
    assert order.bar_high == 112.0
    assert order.bar_low == 108.0
    assert order.bar_close == 111.0
    assert order.bar_is_synthetic is True
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_portfolio.py::test_fill_pending_orders_populates_bar_fields_on_buy tests/test_portfolio.py::test_fill_pending_orders_populates_bar_fields_on_sell -v
```

Expected: FAIL — `assert order.bar_volume == 12_000.0` / `AssertionError` (fields are 0.0 defaults)

- [ ] **Step 3: Implement — populate bar fields in `SimplePortfolio.fill_pending_orders`**

In `trading/impl/simple_portfolio.py`, inside `fill_pending_orders`, replace the two `self._emit(OrderEvent(...))` calls:

**BUY branch** (replace the existing `self._emit(OrderEvent(...))` that sets `direction="BUY"`):

```python
self._emit(OrderEvent(
    symbol           = symbol,
    timestamp        = bar_bundle.timestamp,
    order_type       = "MARKET",
    direction        = "BUY",
    quantity         = delta,
    reference_price  = price,
    bar_volume       = bar.volume,
    bar_high         = bar.high,
    bar_low          = bar.low,
    bar_close        = bar.close,
    bar_is_synthetic = bar.is_synthetic,
))
```

**SELL branch** (replace the existing `self._emit(OrderEvent(...))` that sets `direction="SELL"`):

```python
self._emit(OrderEvent(
    symbol           = symbol,
    timestamp        = bar_bundle.timestamp,
    order_type       = "MARKET",
    direction        = "SELL",
    quantity         = abs(delta),
    reference_price  = price,
    bar_volume       = bar.volume,
    bar_high         = bar.high,
    bar_low          = bar.low,
    bar_close        = bar.close,
    bar_is_synthetic = bar.is_synthetic,
))
```

The HOLD branch (no real order) does not carry bar data — its symbol is `""` and no bar applies.

- [ ] **Step 4: Run all portfolio tests to verify they pass**

```
pytest tests/test_portfolio.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/simple_portfolio.py tests/test_portfolio.py
git commit -m "feat: populate OrderEvent bar fields from fill bar in SimplePortfolio"
```

---

## Task 3: Volume-based slippage in `SimulatedExecutionHandler`

This task implements all four tiers from the spec:
- Tier 1: volume-scaled square-root market impact
- Tier 2: spread floor from high-low range (minimum slippage regardless of order size)
- Tier 4: synthetic bar guard (skip impact, avoid division-by-zero)

**Files:**
- Create: `tests/test_simulated_execution_handler.py`
- Modify: `trading/impl/simulated_execution_handler.py`

**Reference math:**
```
DENOM        = 2 * sqrt(2 * ln(2))  ≈ 2.354820
intraday_vol = (bar_high - bar_low) / bar_close / DENOM
participation = order_quantity / bar_volume
impact_pct   = eta * intraday_vol * sqrt(participation)
spread_floor  = 0.3 * (bar_high - bar_low) / bar_close
base_slippage = max(slippage_pct, spread_floor)
fill_price    = reference_price * (1 + direction_factor * (base_slippage + impact_pct))
```

- [ ] **Step 1: Write the failing tests**

Create `tests/test_simulated_execution_handler.py`:

```python
import math
from datetime import datetime

import pytest

from trading.events import FillEvent, OrderEvent
from trading.impl.simulated_execution_handler import SimulatedExecutionHandler


def _order(
    direction="BUY", quantity=100, reference_price=100.0,
    bar_volume=10_000.0, bar_high=105.0, bar_low=95.0, bar_close=100.0,
    bar_is_synthetic=False,
):
    return OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction=direction, quantity=quantity,
        reference_price=reference_price,
        bar_volume=bar_volume, bar_high=bar_high, bar_low=bar_low,
        bar_close=bar_close, bar_is_synthetic=bar_is_synthetic,
    )


def _handler(commission_pct=0.0, slippage_pct=0.0, market_impact_eta=0.0):
    collected = []
    h = SimulatedExecutionHandler(
        collected.append,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        market_impact_eta=market_impact_eta,
    )
    return h, collected


# --- Constructor -------------------------------------------------------

def test_constructor_accepts_market_impact_eta():
    h, _ = _handler(market_impact_eta=0.1)
    assert h is not None


# --- Tier 4: Synthetic guard -------------------------------------------

def test_synthetic_bar_uses_only_fixed_slippage():
    """Synthetic bar: no impact, no spread floor — only fixed slippage_pct."""
    h, collected = _handler(slippage_pct=0.0005, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="BUY", quantity=100, reference_price=100.0,
        bar_volume=0.0, bar_high=105.0, bar_low=95.0, bar_close=100.0,
        bar_is_synthetic=True,
    ))
    fill = collected[0]
    assert isinstance(fill, FillEvent)
    # fill = 100 * (1 + 0.0005) = 100.05 — no impact applied
    assert abs(fill.fill_price - 100.05) < 1e-9


def test_synthetic_bar_no_division_by_zero():
    """volume=0 on synthetic bar must not raise ZeroDivisionError."""
    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        bar_volume=0.0, bar_is_synthetic=True,
    ))
    assert len(collected) == 1


# --- Tier 2: Spread floor ----------------------------------------------

def test_spread_floor_dominates_fixed_slippage():
    """Wide H-L range → spread floor is larger than slippage_pct."""
    # bar: high=110, low=90, close=100 → spread_floor = 0.3 * 20/100 = 0.06
    # slippage_pct=0.0005 (much smaller); eta=0 so no impact
    h, collected = _handler(slippage_pct=0.0005, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=1, reference_price=100.0,
        bar_volume=10_000.0, bar_high=110.0, bar_low=90.0, bar_close=100.0,
        bar_is_synthetic=False,
    ))
    fill = collected[0]
    # base = max(0.0005, 0.06) = 0.06; impact = 0; fill = 100 * 1.06 = 106.0
    assert abs(fill.fill_price - 106.0) < 1e-9


def test_fixed_slippage_wins_when_range_is_narrow():
    """Narrow H-L range → fixed slippage_pct is larger than spread floor."""
    # bar: high=100.1, low=99.9, close=100 → spread_floor = 0.3 * 0.2/100 = 0.0006
    # slippage_pct=0.001 > 0.0006; eta=0
    h, collected = _handler(slippage_pct=0.001, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=1, reference_price=100.0,
        bar_volume=10_000.0, bar_high=100.1, bar_low=99.9, bar_close=100.0,
        bar_is_synthetic=False,
    ))
    fill = collected[0]
    # base = max(0.001, 0.0006) = 0.001; impact = 0; fill = 100 * 1.001 = 100.1
    assert abs(fill.fill_price - 100.1) < 1e-9


# --- Tier 1: Volume-scaled market impact -------------------------------

def test_large_order_gets_more_slippage_than_small():
    """Higher participation rate → higher market impact → worse fill price."""
    # bar: high=105, low=95, close=100, volume=10_000; eta=0.1; slippage_pct=0
    h_small, c_small = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h_large, c_large = _handler(slippage_pct=0.0, market_impact_eta=0.1)

    common = dict(reference_price=100.0,
                  bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
                  bar_close=100.0, bar_is_synthetic=False)

    h_small.execute_order(_order(direction="BUY", quantity=10, **common))
    h_large.execute_order(_order(direction="BUY", quantity=1_000, **common))

    fill_small = c_small[0].fill_price
    fill_large = c_large[0].fill_price
    assert fill_large > fill_small, (
        f"large order ({fill_large}) should be worse than small ({fill_small})"
    )


def test_market_impact_exact_value():
    """Verify the exact fill price for a known participation rate (eta=0.1)."""
    # bar: high=105, low=95, close=100, volume=10_000
    # sigma = (105-95)/100 / (2*sqrt(2*ln(2))) = 0.1 / 2.354820 ≈ 0.042474
    # participation = 100 / 10_000 = 0.01
    # impact = 0.1 * 0.042474 * sqrt(0.01) = 0.1 * 0.042474 * 0.1 = 0.00042474
    # spread_floor = 0.3 * 10/100 = 0.03
    # base = max(0.0, 0.03) = 0.03 (slippage_pct=0.0)
    # fill = 100 * (1 + 0.03 + 0.00042474) = 103.042474
    DENOM = 2 * (2 * math.log(2)) ** 0.5
    sigma = (105.0 - 95.0) / 100.0 / DENOM
    impact = 0.1 * sigma * (100.0 / 10_000.0) ** 0.5
    spread_floor = 0.3 * (105.0 - 95.0) / 100.0
    expected_fill = 100.0 * (1 + max(0.0, spread_floor) + impact)

    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="BUY", quantity=100, reference_price=100.0,
        bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    assert abs(collected[0].fill_price - expected_fill) < 1e-9


def test_sell_impact_reduces_fill_price():
    """SELL with market impact produces a fill_price below reference_price."""
    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="SELL", quantity=500, reference_price=100.0,
        bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    assert collected[0].fill_price < 100.0


# --- Commission --------------------------------------------------------

def test_commission_computed_on_fill_price_not_reference():
    """Commission is fraction of actual fill_price × quantity."""
    h, collected = _handler(commission_pct=0.001, slippage_pct=0.0, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=10, reference_price=100.0,
        bar_volume=10_000.0, bar_high=100.0, bar_low=100.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    fill = collected[0]
    # spread_floor = 0 (high==low); impact=0; fill_price = 100.0
    assert abs(fill.commission - 100.0 * 10 * 0.001) < 1e-9


# --- HOLD pass-through -------------------------------------------------

def test_hold_order_passes_through_unchanged():
    h, collected = _handler(slippage_pct=0.001, market_impact_eta=0.1)
    h.execute_order(OrderEvent(
        symbol="", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="HOLD", quantity=0,
    ))
    fill = collected[0]
    assert fill.direction == "HOLD"
    assert fill.fill_price == 0.0
    assert fill.commission == 0.0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_simulated_execution_handler.py -v
```

Expected: ALL FAIL — `TypeError: __init__() got an unexpected keyword argument 'market_impact_eta'`

- [ ] **Step 3: Implement the new `SimulatedExecutionHandler`**

Replace the entire contents of `trading/impl/simulated_execution_handler.py`:

```python
import math
from typing import Callable

from ..base.execution import ExecutionHandler
from ..events import Event, FillEvent, OrderEvent

_PARKINSON_DENOM = 2 * (2 * math.log(2)) ** 0.5  # ≈ 2.3548
_SPREAD_FRACTION = 0.3                             # empirical Roll-model constant


class SimulatedExecutionHandler(ExecutionHandler):
    """
    Fills BUY/SELL orders with a two-component cost model:

    1. Spread floor: max(slippage_pct, 0.3 × (high − low) / close)
       Ensures a realistic minimum cost even for tiny orders.

    2. Volume-scaled market impact (Almgren et al.):
       eta × σ × √(order_qty / bar_volume)
       where σ is the Parkinson intraday-volatility estimate.

    Synthetic bars (is_synthetic=True, typically volume=0) skip both
    impact and spread floor, applying only the fixed slippage_pct.

    commission_pct    : fraction of fill value charged per trade, e.g. 0.001 = 0.1%
    slippage_pct      : fixed spread floor (minimum one-way cost), e.g. 0.0005 = 0.05%
    market_impact_eta : square-root impact coefficient; 0.1–0.3 for liquid US equities
    """

    def __init__(
        self,
        emit:               Callable[[Event], None],
        commission_pct:     float = 0.001,
        slippage_pct:       float = 0.0005,
        market_impact_eta:  float = 0.1,
    ):
        super().__init__(emit)
        self._commission_pct    = commission_pct
        self._slippage_pct      = slippage_pct
        self._market_impact_eta = market_impact_eta

    def execute_order(self, event: OrderEvent) -> None:
        if event.direction == "HOLD":
            self._emit(FillEvent(
                symbol     = event.symbol,
                timestamp  = event.timestamp,
                direction  = "HOLD",
                quantity   = 0,
                fill_price = 0.0,
                commission = 0.0,
            ))
            return

        direction_factor = 1 if event.direction == "BUY" else -1

        if event.bar_is_synthetic:
            # Synthetic bar: no real price discovery → fixed slippage only
            total_slippage = self._slippage_pct
        else:
            spread_floor = (
                _SPREAD_FRACTION * (event.bar_high - event.bar_low) / event.bar_close
                if event.bar_close > 0 else 0.0
            )
            base_slippage = max(self._slippage_pct, spread_floor)

            if event.bar_volume > 0 and self._market_impact_eta > 0:
                intraday_vol = (
                    (event.bar_high - event.bar_low) / event.bar_close / _PARKINSON_DENOM
                    if event.bar_close > 0 else 0.0
                )
                participation = event.quantity / event.bar_volume
                impact_pct = self._market_impact_eta * intraday_vol * participation ** 0.5
            else:
                impact_pct = 0.0

            total_slippage = base_slippage + impact_pct

        fill_price = event.reference_price * (1 + direction_factor * total_slippage)
        commission = fill_price * event.quantity * self._commission_pct

        self._emit(FillEvent(
            symbol     = event.symbol,
            timestamp  = event.timestamp,
            direction  = event.direction,
            quantity   = event.quantity,
            fill_price = fill_price,
            commission = commission,
        ))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_simulated_execution_handler.py -v
```

Expected: ALL PASS

- [ ] **Step 5: Run the full test suite to check nothing is broken**

```
pytest tests/ -v --ignore=tests/test_yahoo_external.py
```

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add trading/impl/simulated_execution_handler.py tests/test_simulated_execution_handler.py
git commit -m "feat: volume-scaled square-root market impact + spread floor + synthetic guard"
```

---

## Task 4: Wire `market_impact_eta` in `run_backtest.py`

**Files:**
- Modify: `run_backtest.py`

- [ ] **Step 1: Add `MARKET_IMPACT_ETA` constant**

In `run_backtest.py`, replace the configuration block:

```python
# --- Configuration -----------------------------------------------------------
SYMBOLS            = ["AAPL", "MSFT"]
START              = "2020-01-01"
END                = "2022-01-01"
INITIAL_CAPITAL    = 10_000.0
FAST_WINDOW        = 10
SLOW_WINDOW        = 30
COMMISSION_PCT     = 0.001  # 0.1% of trade value per fill
SLIPPAGE_PCT       = 0.0005 # fixed spread floor (one-way minimum cost)
MARKET_IMPACT_ETA  = 0.1    # square-root impact coefficient (Almgren et al.)
RESULTS_DIR        = "results"
RESULTS_FORMAT     = "parquet"  # "parquet" or "csv"
# -----------------------------------------------------------------------------
```

- [ ] **Step 2: Wire the new parameter into `SimulatedExecutionHandler`**

Replace the existing `SimulatedExecutionHandler` construction line:

```python
execution = SimulatedExecutionHandler(
    events.put,
    commission_pct    = COMMISSION_PCT,
    slippage_pct      = SLIPPAGE_PCT,
    market_impact_eta = MARKET_IMPACT_ETA,
)
```

- [ ] **Step 3: Verify the backtest runs end-to-end**

```
python run_backtest.py
```

Expected: backtest completes without errors and writes result files to `results/`.

- [ ] **Step 4: Commit**

```bash
git add run_backtest.py
git commit -m "feat: wire market_impact_eta into SimulatedExecutionHandler in run_backtest"
```

---

## Self-Review

**Spec coverage:**

| Spec requirement | Covered by |
|---|---|
| Volume-scaled √ market impact (Tier 1) | Task 3 — `impact_pct = eta × σ × √(participation)` |
| Spread floor from H-L range (Tier 2) | Task 3 — `base = max(slippage_pct, 0.3 × (H−L)/C)` |
| Synthetic bar guard / zero-volume crash (Tier 4) | Task 3 — `if event.bar_is_synthetic: total_slippage = slippage_pct` |
| Bar data available in execution handler | Task 1 + Task 2 — `OrderEvent` fields populated by portfolio |
| Suggested constructor signature | Task 3 + Task 4 — `commission_pct`, `slippage_pct`, `market_impact_eta` |
| `reference_price = bar.open` (not close) | Unchanged — portfolio already sets this correctly |

**Tier 3 (per-symbol slippage_pct) is explicitly out of scope** — the spec marks it "Medium complexity" and the suggested constructor does not include it.

**Placeholder scan:** All test functions contain exact numeric assertions computed from the formula. All implementation blocks are complete.

**Type consistency:** `event.bar_volume`, `event.bar_high`, `event.bar_low`, `event.bar_close`, `event.bar_is_synthetic` are defined in Task 1 and used identically in Tasks 2 and 3.
