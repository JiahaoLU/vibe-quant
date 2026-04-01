# Fix Zero-Fill Contamination: Carry-Forward + History Guard

Date: 2026-03-31

## Problem

When a symbol has no bar at a timestamp, both `YahooDataHandler` and `MultiCSVDataHandler` insert a synthetic `TickEvent` with all prices `= 0.0`. These zero bars flow into the history deque and get returned by `get_latest_bars`, distorting SMA calculations silently — no error, wrong signal. Also corrupts mark-to-market in `on_fill` (uses `get_latest_bars` for equity snapshot).

### Root cause (identical in both handlers)

```python
# __init__ — both YahooDataHandler and MultiCSVDataHandler
bundle = {
    symbol: raw[symbol].get(
        ts,
        TickEvent(symbol=symbol, timestamp=ts, open=0.0, ..., close=0.0, volume=0.0),  # ← zero-fill
    )
    for symbol in symbols
}

# update_bars — both handlers
for symbol, bar in bars.items():
    self._history[symbol].append(bar)  # ← zero bars enter deque
```

## Fix

Two parts:
1. **Carry-forward**: replace zero-fill with last known real bar (prices valid); mark synthetic bars with `is_synthetic=True`
2. **Skip from history**: don't push synthetic bars into the deque; `get_latest_bars` returns only real bars

## Files to change

| File | Change |
|---|---|
| `trading/events.py` | Add `is_synthetic: bool = False` to `TickEvent` |
| `trading/impl/yahoo_data_handler.py` | Carry-forward in `__init__`; skip synthetic in `update_bars` |
| `trading/impl/multi_csv_data_handler.py` | Same |
| `strategies/sma_crossover_strategy.py` | Guard: skip symbol if any close ≤ 0 |
| `tests/test_data.py` | Update 1 test; add 2 new tests |
| `tests/test_yahoo_data_handler.py` | Update 1 test; add 1 new test |

## Implementation

### 1. `trading/events.py`

Add `is_synthetic: bool = False` at the end of `TickEvent`. Default `False` keeps all existing construction sites backward-compatible.

```python
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
```

### 2. Both data handlers — `__init__`

Replace the dict-comprehension zero-fill with a loop that carries forward the last real bar:

```python
last_real: dict[str, TickEvent | None] = {s: None for s in symbols}
self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
for ts in timeline:
    bundle: dict[str, TickEvent] = {}
    for symbol in symbols:
        if ts in raw[symbol]:
            bar = raw[symbol][ts]
            last_real[symbol] = bar
            bundle[symbol] = bar
        elif last_real[symbol] is not None:
            prev = last_real[symbol]
            bundle[symbol] = TickEvent(
                symbol=symbol, timestamp=ts,
                open=prev.close, high=prev.close, low=prev.close, close=prev.close,
                volume=0.0, is_synthetic=True,
            )
        else:
            # No prior real bar to carry forward (first timestamp for this symbol)
            bundle[symbol] = TickEvent(
                symbol=symbol, timestamp=ts,
                open=0.0, high=0.0, low=0.0, close=0.0,
                volume=0.0, is_synthetic=True,
            )
    self._merged.append((ts, bundle))
```

`last_real` is a local variable — only needed during construction.

Carry-forward bar: open=high=low=close=prev.close, volume=0. Represents "no trading; price flat at last close."

### 3. Both data handlers — `update_bars`

Skip synthetic bars when updating the deque:

```python
def update_bars(self) -> bool:
    if self._index >= len(self._merged):
        return False
    ts, bars = self._merged[self._index]
    self._index += 1
    for symbol, bar in bars.items():
        if not bar.is_synthetic:
            self._history[symbol].append(bar)
    self._emit(BarBundleEvent(timestamp=ts, bars=bars))
    return True
```

The `BarBundleEvent` still carries the carry-forward bar (so `fill_pending_orders` has a price). Only the deque is kept clean.

### 4. `strategies/sma_crossover_strategy.py`

Add a defensive guard after extracting closes:

```python
closes = [b.close for b in bars]
if any(c <= 0 for c in closes):
    continue
fast_sma = sum(closes[-self._fast:]) / self._fast
slow_sma = sum(closes) / self._slow
```

With the data handler fix, real bars always have positive closes. This guard is a safety net for malformed CSV data.

### 5. `tests/test_data.py`

**Update `test_missing_symbol_bar_is_zero_filled`** → rename and change assertions:

```python
def test_missing_symbol_bar_is_carry_forwarded():
    """Missing bar uses last known real price, not zero."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — both present
        events.get_nowait()
        handler.update_bars()  # 2020-01-03 — MSFT missing
        bundle = events.get_nowait()
        assert bundle.bars["AAPL"].close == 101.0
        assert bundle.bars["AAPL"].is_synthetic is False
        assert bundle.bars["MSFT"].close == 200.5   # carry-forward from 2020-01-02
        assert bundle.bars["MSFT"].is_synthetic is True
    finally:
        os.unlink(aapl)
        os.unlink(msft)
```

**Add `test_synthetic_bar_excluded_from_history`**:

```python
def test_synthetic_bar_excluded_from_history():
    """Synthetic (carry-forward) bars are not stored in the deque."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — MSFT real
        handler.update_bars()  # 2020-01-03 — MSFT synthetic (skipped from deque)
        bars = handler.get_latest_bars("MSFT", 5)
        assert len(bars) == 1                        # only the Jan 2 real bar
        assert bars[0].close == 200.5
        assert bars[0].is_synthetic is False
    finally:
        os.unlink(aapl)
        os.unlink(msft)
```

**Add `test_real_bar_after_gap_resumes_history`**:

```python
def test_real_bar_after_gap_resumes_history():
    """A real bar after a synthetic gap resumes history normally."""
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        events = queue.Queue()
        handler = MultiCSVDataHandler(events.put, ["AAPL", "MSFT"], [aapl, msft])
        handler.update_bars()  # 2020-01-02 — MSFT real
        handler.update_bars()  # 2020-01-03 — MSFT synthetic
        handler.update_bars()  # 2020-01-04 — MSFT real again
        bars = handler.get_latest_bars("MSFT", 5)
        assert len(bars) == 2                        # Jan 2 and Jan 4 — no synthetic
        assert bars[0].close == 200.5                # Jan 2
        assert bars[1].close == 201.0                # Jan 4
    finally:
        os.unlink(aapl)
        os.unlink(msft)
```

### 6. `tests/test_yahoo_data_handler.py`

Update `test_handler_missing_bar_is_zero_filled` to assert carry-forward and `is_synthetic`. Add `test_handler_synthetic_bar_excluded_from_history` with the same pattern as the CSV version.

## Edge cases

| Scenario | Behavior |
|---|---|
| First timestamp for a symbol (no prior bar) | Synthetic zero bar (`is_synthetic=True`), not added to deque; strategy stays in warm-up |
| Symbol suspended for N bars | Only real bars in deque; strategy stays in warm-up or hold — correct |
| CSV data with zero close | Enters deque as real bar; strategy guard `if any(c <= 0) continue` skips it |
| Carry-forward used in `fill_pending_orders` | `bar.open = prev.close` — stale but valid price; better than 0.0 |
| Mark-to-market in `on_fill` | `get_latest_bars` returns last real bar; stale price but no longer 0.0 |

## Verification

```bash
# 1. Run full test suite
python -m pytest tests/ -v

# 2. Run backtest — return should be unchanged (AAPL and MSFT have no gaps in Yahoo daily data for 2020-2022)
python run_backtest.py
```
