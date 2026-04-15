# Mixed Daily + Intraday Strategies Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow `StrategyContainer` to hold both daily (`bar_freq="1d"`) and intraday (`bar_freq="Xm"`) strategies simultaneously, dispatching daily strategies only on end-of-day bars.

**Architecture:** `BarBundleEvent.is_end_of_day` becomes the dispatch gate for daily strategies inside an intraday container. Backtest handlers detect EOD via date lookahead over the preloaded timeline (no market-hours knowledge needed). The live handler (`AlpacaDataHandler`) detects EOD by checking whether the bar's time slot ends at or after market close, using constants extracted to a new `trading/market_hours.py`. `StrategyContainer` tracks which strategies are EOD-gated and skips them on non-EOD bars; `_steps` is still computed for those strategies so `get_bars` aggregation remains correct.

**Tech Stack:** Python stdlib only (`zoneinfo`, `datetime`). No new dependencies.

---

## File Map

| Action | File | Change |
|--------|------|--------|
| Create | `trading/market_hours.py` | Market timezone + close/fetch time constants |
| Modify | `trading/impl/data_handler/alpaca_data_handler.py` | Import from `market_hours`; set `is_end_of_day` on emitted intraday bars |
| Modify | `trading/impl/data_handler/yahoo_data_handler.py` | Set `is_end_of_day` via date lookahead in `update_bars` |
| Modify | `trading/impl/data_handler/multi_csv_data_handler.py` | Same date-lookahead pattern as Yahoo |
| Modify | `trading/impl/strategy_signal_generator/strategy_container.py` | Remove `ValueError` from `required_freq`; add `_is_eod_gated` list; EOD dispatch in `get_signals` |
| Modify | `tests/test_strategy_container_bar_freq.py` | Update test that asserts ValueError; add mixed-container tests |
| Create | `tests/test_market_hours.py` | Sanity-check constants are importable and correct types |
| Modify | `tests/test_alpaca_data_handler.py` | Add `is_end_of_day` correctness tests |
| Modify | `tests/test_yahoo_data_handler.py` | Add `is_end_of_day` correctness tests |

---

## Task 1: Create `trading/market_hours.py`

**Files:**
- Create: `trading/market_hours.py`
- Create: `tests/test_market_hours.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_market_hours.py
from zoneinfo import ZoneInfo

def test_market_hours_constants_exist_and_have_correct_types():
    from trading.market_hours import (
        MARKET_TZ,
        MARKET_CLOSE_HOUR,
        MARKET_CLOSE_MINUTE,
        DAILY_BAR_FETCH_HOUR,
        DAILY_BAR_FETCH_MINUTE,
    )
    assert isinstance(MARKET_TZ, ZoneInfo)
    assert isinstance(MARKET_CLOSE_HOUR, int)
    assert isinstance(MARKET_CLOSE_MINUTE, int)
    assert isinstance(DAILY_BAR_FETCH_HOUR, int)
    assert isinstance(DAILY_BAR_FETCH_MINUTE, int)
    assert MARKET_CLOSE_HOUR == 16
    assert MARKET_CLOSE_MINUTE == 0
    assert DAILY_BAR_FETCH_HOUR == 16
    assert DAILY_BAR_FETCH_MINUTE == 5
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_market_hours.py -v
```
Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write the module**

```python
# trading/market_hours.py
from zoneinfo import ZoneInfo

MARKET_TZ           = ZoneInfo("America/New_York")
MARKET_CLOSE_HOUR   = 16
MARKET_CLOSE_MINUTE = 0
DAILY_BAR_FETCH_HOUR   = 16
DAILY_BAR_FETCH_MINUTE = 5
```

- [ ] **Step 4: Run test to verify it passes**

```bash
pytest tests/test_market_hours.py -v
```
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add trading/market_hours.py tests/test_market_hours.py
git commit -m "feat: add market_hours module with ET timezone and close/fetch time constants"
```

---

## Task 2: Update `AlpacaDataHandler` — import from `market_hours`, set `is_end_of_day`

**Files:**
- Modify: `trading/impl/data_handler/alpaca_data_handler.py`
- Modify: `tests/test_alpaca_data_handler.py`

**Background:** Currently `ET`, `_DAILY_BAR_HOUR`, and `_DAILY_BAR_MINUTE` are module-level constants in `alpaca_data_handler.py`. Replace them with imports from `market_hours`. Then set `is_end_of_day=True` on emitted `BarBundleEvent` only when the bar is the last bar of the trading session:
- Daily bars (`bar_freq="1d"`): always `True`.
- Intraday bars: `True` when `bar_ts.hour * 60 + bar_ts.minute + bar_minutes >= MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE` (i.e., the bar's end time is at or after market close). For a 5m bar at 15:55: `15*60 + 55 + 5 = 960 = 16*60`. ✓

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_alpaca_data_handler.py`:

```python
def test_update_bars_async_sets_is_end_of_day_true_for_daily_bar():
    """Daily bars always have is_end_of_day=True."""
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from datetime import timezone

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append, symbols=["AAPL"], bar_freq="1d",
        api_key="key", secret="secret",
    )
    raw = {
        "AAPL": {
            "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert collected[0].is_end_of_day is True


def test_update_bars_async_sets_is_end_of_day_true_for_last_intraday_bar():
    """Intraday bar whose slot ends at market close has is_end_of_day=True.

    For 5m bars, the last bar starts at 15:55 ET (15:55 + 5m = 16:00 = close).
    Alpaca returns timestamps in UTC; 15:55 ET = 19:55 UTC in winter.
    """
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from zoneinfo import ZoneInfo

    ET = ZoneInfo("America/New_York")
    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append, symbols=["AAPL"], bar_freq="5m",
        api_key="key", secret="secret",
    )
    # 15:55 ET on a non-DST day = 20:55 UTC
    last_bar_ts = datetime(2024, 1, 2, 20, 55, tzinfo=ZoneInfo("UTC"))
    raw = {
        "AAPL": {
            "timestamp": last_bar_ts,
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert collected[0].is_end_of_day is True


def test_update_bars_async_sets_is_end_of_day_false_for_mid_session_intraday_bar():
    """Intraday bar in the middle of the session has is_end_of_day=False."""
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from zoneinfo import ZoneInfo

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append, symbols=["AAPL"], bar_freq="5m",
        api_key="key", secret="secret",
    )
    # 10:00 ET = 15:00 UTC (mid-session)
    mid_bar_ts = datetime(2024, 1, 2, 15, 0, tzinfo=ZoneInfo("UTC"))
    raw = {
        "AAPL": {
            "timestamp": mid_bar_ts,
            "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0,
        }
    }
    with (
        patch("trading.impl.data_handler.alpaca_data_handler.fetch_bars", return_value=raw),
        patch.object(handler, "_seconds_until_next_bar", return_value=0.0),
    ):
        asyncio.run(handler.update_bars_async())

    assert collected[0].is_end_of_day is False
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_alpaca_data_handler.py::test_update_bars_async_sets_is_end_of_day_true_for_daily_bar tests/test_alpaca_data_handler.py::test_update_bars_async_sets_is_end_of_day_true_for_last_intraday_bar tests/test_alpaca_data_handler.py::test_update_bars_async_sets_is_end_of_day_false_for_mid_session_intraday_bar -v
```
Expected: all FAIL (AssertionError — `is_end_of_day` is always `True`)

- [ ] **Step 3: Update `alpaca_data_handler.py`**

Replace the top of the file:

```python
# Remove these three module-level constants:
#   ET = ZoneInfo("America/New_York")
#   _DAILY_BAR_HOUR   = 16
#   _DAILY_BAR_MINUTE = 5

# Replace the ZoneInfo import + constants with:
from trading.market_hours import (
    MARKET_TZ,
    MARKET_CLOSE_HOUR,
    MARKET_CLOSE_MINUTE,
    DAILY_BAR_FETCH_HOUR,
    DAILY_BAR_FETCH_MINUTE,
)
```

In `prefill`, replace `ET` → `MARKET_TZ`:
```python
now = datetime.now(tz=MARKET_TZ)
```

In `update_bars_async`, replace `ET` → `MARKET_TZ` and add EOD detection before emitting:
```python
now = datetime.now(tz=MARKET_TZ)
# ... existing fetch logic unchanged ...

if bundle_bars:
    ts = next(iter(bundle_bars.values())).timestamp
    if self._bar_freq == "1d":
        is_eod = True
    else:
        bar_minutes = int(self._bar_freq.rstrip("m"))
        ts_et = ts.astimezone(MARKET_TZ)
        close_minutes = MARKET_CLOSE_HOUR * 60 + MARKET_CLOSE_MINUTE
        is_eod = ts_et.hour * 60 + ts_et.minute + bar_minutes >= close_minutes
    self._emit(BarBundleEvent(timestamp=ts, bars=bundle_bars, is_end_of_day=is_eod))
```

In `_seconds_until_next_bar`, replace `ET` → `MARKET_TZ`, `_DAILY_BAR_HOUR` → `DAILY_BAR_FETCH_HOUR`, `_DAILY_BAR_MINUTE` → `DAILY_BAR_FETCH_MINUTE`:
```python
def _seconds_until_next_bar(self) -> float:
    now = datetime.now(tz=MARKET_TZ)
    if self._bar_freq == "1d":
        target = now.replace(hour=DAILY_BAR_FETCH_HOUR, minute=DAILY_BAR_FETCH_MINUTE,
                             second=0, microsecond=0)
        if now >= target:
            target += timedelta(days=1)
            while target.weekday() >= 5:
                target += timedelta(days=1)
        return max(0.0, (target - now).total_seconds())
    else:
        minutes = int(self._bar_freq.rstrip("m"))
        next_min = ((now.minute // minutes) + 1) * minutes
        delta_min = next_min - now.minute
        target = now.replace(second=0, microsecond=0) + timedelta(minutes=delta_min)
        return max(0.0, (target - now).total_seconds())
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_alpaca_data_handler.py -v
```
Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/data_handler/alpaca_data_handler.py tests/test_alpaca_data_handler.py
git commit -m "feat: alpaca_data_handler sets is_end_of_day correctly; imports market_hours constants"
```

---

## Task 3: Update backtest handlers to set `is_end_of_day` via date lookahead

**Files:**
- Modify: `trading/impl/data_handler/yahoo_data_handler.py`
- Modify: `trading/impl/data_handler/multi_csv_data_handler.py`
- Modify: `tests/test_yahoo_data_handler.py`

**Background:** Both handlers preload the full timeline into `self._merged` (a `list[tuple[datetime, dict]]`). In `update_bars`, set `is_end_of_day=True` when the next entry in `_merged` is on a different calendar date (or when this is the last entry). For `bar_freq="1d"` each entry is a different date, so every bar is EOD. No market-hours constants needed.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_yahoo_data_handler.py`:

```python
def test_update_bars_daily_bars_always_end_of_day():
    """Every daily bar emitted by YahooDataHandler has is_end_of_day=True."""
    from trading.impl.data_handler.yahoo_data_handler import YahooDataHandler

    rows = {
        "AAPL": [
            {"timestamp": datetime(2020, 1, 2), "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 1000.0},
            {"timestamp": datetime(2020, 1, 3), "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 1100.0},
        ]
    }
    collected = []
    handler = YahooDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-04",
        fetch=lambda syms, start, end, freq: rows,
        bar_freq="1d",
    )
    while handler.update_bars():
        pass

    assert all(e.is_end_of_day for e in collected)


def test_update_bars_intraday_only_last_bar_of_day_is_eod():
    """For intraday data, only the last bar in each calendar day has is_end_of_day=True."""
    from trading.impl.data_handler.yahoo_data_handler import YahooDataHandler

    rows = {
        "AAPL": [
            # Day 1: three 5m bars
            {"timestamp": datetime(2020, 1, 2, 9, 30), "open": 100.0, "high": 100.5, "low": 99.5, "close": 100.2, "volume": 100.0},
            {"timestamp": datetime(2020, 1, 2, 9, 35), "open": 100.2, "high": 100.8, "low": 100.0, "close": 100.5, "volume": 110.0},
            {"timestamp": datetime(2020, 1, 2, 9, 40), "open": 100.5, "high": 101.0, "low": 100.3, "close": 100.9, "volume": 120.0},
            # Day 2: two 5m bars
            {"timestamp": datetime(2020, 1, 3, 9, 30), "open": 101.0, "high": 101.5, "low": 100.8, "close": 101.2, "volume": 130.0},
            {"timestamp": datetime(2020, 1, 3, 9, 35), "open": 101.2, "high": 101.8, "low": 101.0, "close": 101.5, "volume": 140.0},
        ]
    }
    collected = []
    handler = YahooDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-04",
        fetch=lambda syms, start, end, freq: rows,
        bar_freq="5m",
    )
    while handler.update_bars():
        pass

    eod_flags = [e.is_end_of_day for e in collected]
    # 5 bars total: [False, False, True, False, True]
    assert eod_flags == [False, False, True, False, True]
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_yahoo_data_handler.py::test_update_bars_daily_bars_always_end_of_day tests/test_yahoo_data_handler.py::test_update_bars_intraday_only_last_bar_of_day_is_eod -v
```
Expected: FAIL (`assert all(...)` passes but the second test fails — all bars currently have `is_end_of_day=True`)

- [ ] **Step 3: Update `yahoo_data_handler.update_bars`**

Replace the `update_bars` method:

```python
def update_bars(self) -> bool:
    if self._index >= len(self._merged):
        return False
    ts, bars = self._merged[self._index]
    self._index += 1
    is_eod = (
        self._index >= len(self._merged)
        or self._merged[self._index][0].date() != ts.date()
    )
    for symbol, bar in bars.items():
        if not bar.is_synthetic:
            self._history[symbol].append(bar)
    self._emit(BarBundleEvent(timestamp=ts, bars=bars, is_end_of_day=is_eod))
    return True
```

- [ ] **Step 4: Apply the identical pattern to `multi_csv_data_handler.update_bars`**

```python
def update_bars(self) -> bool:
    if self._index >= len(self._merged):
        return False
    ts, bars = self._merged[self._index]
    self._index += 1
    is_eod = (
        self._index >= len(self._merged)
        or self._merged[self._index][0].date() != ts.date()
    )
    for symbol, bar in bars.items():
        if not bar.is_synthetic:
            self._history[symbol].append(bar)
    self._emit(BarBundleEvent(timestamp=ts, bars=bars, is_end_of_day=is_eod))
    return True
```

- [ ] **Step 5: Run all data handler tests**

```bash
pytest tests/test_yahoo_data_handler.py tests/test_data.py tests/test_data_handler_bar_freq.py -v
```
Expected: all PASS

- [ ] **Step 6: Commit**

```bash
git add trading/impl/data_handler/yahoo_data_handler.py trading/impl/data_handler/multi_csv_data_handler.py tests/test_yahoo_data_handler.py
git commit -m "feat: backtest data handlers set is_end_of_day via date lookahead"
```

---

## Task 4: Update `StrategyContainer` — allow mixed containers, dispatch daily strategies on EOD

**Files:**
- Modify: `trading/impl/strategy_signal_generator/strategy_container.py`
- Modify: `tests/test_strategy_container_bar_freq.py`

**Background:**

Three changes to `strategy_container.py`:

1. **`required_freq`**: Remove the `ValueError` for mixed daily+intraday. For mixed containers, return the finest intraday freq. An all-daily container still returns `"1d"`.

2. **`_is_eod_gated: list[bool]`**: New parallel list alongside `_steps`. `_is_eod_gated[i] = True` when strategy `i` is daily (`bar_freq="1d"`) and the container's `required_freq` is intraday. Computed in `_recompute_steps`. `_steps[i]` is still computed as `390 // req_minutes` for such strategies so `get_bars` aggregation remains correct.

3. **`get_signals`**: For EOD-gated strategies, `continue` when `not event.is_end_of_day` instead of checking `_bar_count % steps`.

- [ ] **Step 1: Update the existing test that asserts ValueError**

In `tests/test_strategy_container_bar_freq.py`, replace:

```python
def test_required_freq_raises_when_mixing_daily_and_intraday():
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    with pytest.raises(ValueError, match="Cannot mix"):
        _ = container.required_freq
```

with:

```python
def test_required_freq_returns_intraday_freq_when_mixing_daily_and_intraday():
    """Mixed daily+intraday container returns the finest intraday freq — no error."""
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    assert container.required_freq == "5m"


def test_required_freq_returns_finest_intraday_when_mixed_with_multiple_intraday():
    """With both daily and multiple intraday strategies, returns the finest intraday."""
    container = _make_container()
    container.add(_Stub, StrategyParams(symbols=["AAPL"], name="a", bar_freq="1d"))
    container.add(_Stub, StrategyParams(symbols=["MSFT"], name="b", bar_freq="5m"))
    container.add(_Stub, StrategyParams(symbols=["GOOG"], name="c", bar_freq="1m"))
    assert container.required_freq == "1m"
```

- [ ] **Step 2: Add new dispatch behaviour tests**

Add to `tests/test_strategy_container_bar_freq.py`:

```python
def _bundle_eod(symbols: list[str], eod: bool) -> BarBundleEvent:
    ts = datetime(2024, 1, 2, 9, 30)
    return BarBundleEvent(
        timestamp=ts,
        bars={
            s: TickEvent(symbol=s, timestamp=ts,
                         open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
            for s in symbols
        },
        is_end_of_day=eod,
    )


def test_daily_strategy_in_mixed_container_fires_only_on_eod_bars():
    """A '1d' strategy in a mixed container fires when is_end_of_day=True, skips otherwise."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(1)
            return None

    container = _make_container()
    container.add(_Stub,    StrategyParams(symbols=["AAPL"], name="intra", bar_freq="5m"))
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="daily", bar_freq="1d"))

    # 4 non-EOD bars, then 1 EOD bar
    for _ in range(4):
        container.get_signals(_bundle_eod(["AAPL"], eod=False))
    assert calls == []

    container.get_signals(_bundle_eod(["AAPL"], eod=True))
    assert len(calls) == 1


def test_intraday_strategy_in_mixed_container_fires_on_every_bar():
    """The intraday strategy in a mixed container fires on every bar regardless of is_end_of_day."""
    calls = []

    class _Counter(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event):
            calls.append(1)
            return None

    container = _make_container()
    container.add(_Counter, StrategyParams(symbols=["AAPL"], name="intra", bar_freq="5m"))
    container.add(_Stub,    StrategyParams(symbols=["AAPL"], name="daily", bar_freq="1d"))

    for eod in [False, False, False, False, True]:
        container.get_signals(_bundle_eod(["AAPL"], eod=eod))

    assert len(calls) == 5


def test_daily_strategy_on_get_signal_not_called_on_non_eod_bars():
    """on_get_signal must not fire for a daily strategy on non-EOD bars."""
    hook_calls = []

    class _Tracking(Strategy):
        def _init(self, p): pass
        def calculate_signals(self, event): return None
        def on_get_signal(self, result):
            hook_calls.append(result)

    container = _make_container()
    container.add(_Stub,     StrategyParams(symbols=["AAPL"], name="intra", bar_freq="5m"))
    container.add(_Tracking, StrategyParams(symbols=["AAPL"], name="daily", bar_freq="1d"))

    for _ in range(4):
        container.get_signals(_bundle_eod(["AAPL"], eod=False))
    assert hook_calls == []

    container.get_signals(_bundle_eod(["AAPL"], eod=True))
    assert len(hook_calls) == 1
```

- [ ] **Step 3: Run new tests to verify they fail**

```bash
pytest tests/test_strategy_container_bar_freq.py::test_required_freq_returns_intraday_freq_when_mixing_daily_and_intraday tests/test_strategy_container_bar_freq.py::test_daily_strategy_in_mixed_container_fires_only_on_eod_bars tests/test_strategy_container_bar_freq.py::test_intraday_strategy_in_mixed_container_fires_on_every_bar tests/test_strategy_container_bar_freq.py::test_daily_strategy_on_get_signal_not_called_on_non_eod_bars -v
```
Expected: FAIL

- [ ] **Step 4: Update `required_freq` in `strategy_container.py`**

Replace the `required_freq` property:

```python
@property
def required_freq(self) -> str:
    if not self._strategies:
        return "1d"
    freqs = [s.strategy_params.bar_freq for s, _ in self._strategies]
    intraday = [f for f in freqs if f != "1d"]
    if not intraday:
        return "1d"
    minutes = [_bar_freq_to_minutes(f) for f in intraday]
    return f"{min(minutes)}m"
```

- [ ] **Step 5: Add `_is_eod_gated` to `__init__` and `_recompute_steps`**

In `__init__`, add after `self._steps: list[int] = []`:
```python
self._is_eod_gated: list[bool] = []
```

Replace `_recompute_steps`:

```python
def _recompute_steps(self) -> None:
    if not self._strategies:
        self._steps = []
        self._is_eod_gated = []
        return
    req_freq = self.required_freq
    if req_freq == "1d":
        self._steps = [1] * len(self._strategies)
        self._is_eod_gated = [False] * len(self._strategies)
        return
    req_minutes = _bar_freq_to_minutes(req_freq)
    self._steps = [
        _bar_freq_to_minutes(s.strategy_params.bar_freq) // req_minutes
        for s, _ in self._strategies
    ]
    self._is_eod_gated = [
        s.strategy_params.bar_freq == "1d"
        for s, _ in self._strategies
    ]
```

- [ ] **Step 6: Update `get_signals` dispatch**

In `get_signals`, replace the per-strategy dispatch block:

```python
for i, (strategy, _) in enumerate(self._strategies):
    steps = self._steps[i] if self._steps else 1
    eod_gated = self._is_eod_gated[i] if self._is_eod_gated else False
    if eod_gated:
        if not event.is_end_of_day:
            continue
    elif self._bar_count % steps != 0:
        continue
    result = strategy.calculate_signals(event)
    strategy.on_get_signal(result)
    if result is not None:
        any_new = True
        for symbol, sig in result.signals.items():
            self._carried[i][symbol] = sig.signal
```

- [ ] **Step 7: Run all strategy container tests**

```bash
pytest tests/test_strategy_container_bar_freq.py tests/test_strategy_container.py -v
```
Expected: all PASS

- [ ] **Step 8: Run the full test suite**

```bash
pytest -v
```
Expected: all PASS. If any test asserts `ValueError` for mixing daily+intraday, it's stale — update it to expect the intraday freq instead.

- [ ] **Step 9: Commit**

```bash
git add trading/impl/strategy_signal_generator/strategy_container.py tests/test_strategy_container_bar_freq.py
git commit -m "feat: StrategyContainer allows mixed daily+intraday; dispatches daily strategies on is_end_of_day"
```

---

## Self-Review

**Spec coverage:**
- ✓ tz_config file (`trading/market_hours.py`) with ET, close hour/minute, fetch hour/minute
- ✓ Daily trading = 1 event per 24 hours; start/timing derived from tz_config for live, date-lookahead for backtest
- ✓ Intraday trading dispatch unchanged (step count path unchanged)
- ✓ Mixed containers allowed; `required_freq` returns finest intraday
- ✓ `is_end_of_day` set correctly by all three data handlers

**Placeholder scan:** No TBDs. All code blocks complete.

**Type consistency:**
- `_is_eod_gated: list[bool]` — initialized in `__init__`, populated in `_recompute_steps`, read in `get_signals`. Consistent.
- `MARKET_TZ`, `MARKET_CLOSE_HOUR`, etc. — defined in Task 1, imported in Task 2. Names match.
- `is_end_of_day` keyword arg passed to `BarBundleEvent(...)` — field exists on `BarBundleEvent` in `trading/events.py:36`. Consistent.
