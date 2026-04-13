# Historical Bar Pre-loading at Startup Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pre-populate `AlpacaDataHandler` deques with `max_history` bars of historical data at startup so strategies with long lookback windows receive correct signals from the first live bar.

**Architecture:** Add `fetch_bars_history()` to `external/alpaca.py` (returns all bars in a window, not just the last); add `prefill()` to `AlpacaDataHandler` that calls it and fills deques; call `prefill()` from `LiveRunner.run()` after reconciliation and before the polling loop. No changes to the `DataHandler` ABC or any strategy code.

**Tech Stack:** alpaca-py SDK (`StockHistoricalDataClient`), Python stdlib (`datetime`, `timedelta`, `deque`), `unittest.mock` for tests.

---

## File Map

| File | Change |
|---|---|
| `external/alpaca.py` | Add `fetch_bars_history()` — returns `dict[str, list[dict]]` |
| `trading/impl/data_handler/alpaca_data_handler.py` | Import `fetch_bars_history`; add `prefill()` method |
| `trading/live_runner.py` | Call `self._data.prefill()` after `reconciler.hydrate()` |
| `tests/test_alpaca_external.py` | Tests for `fetch_bars_history` |
| `tests/test_alpaca_data_handler.py` | Tests for `prefill()` |
| `tests/test_live_runner.py` | Test that `prefill()` is called at startup |

---

### Task 1: `fetch_bars_history` in `external/alpaca.py`

**Files:**
- Modify: `external/alpaca.py`
- Test: `tests/test_alpaca_external.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_alpaca_external.py`:

```python
def test_fetch_bars_history_returns_all_bars_in_window():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()

    bar1 = MagicMock()
    bar1.timestamp = datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)
    bar1.open, bar1.high, bar1.low, bar1.close, bar1.volume = 100.0, 101.0, 99.0, 100.5, 50000

    bar2 = MagicMock()
    bar2.timestamp = datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc)
    bar2.open, bar2.high, bar2.low, bar2.close, bar2.volume = 101.0, 102.0, 100.0, 101.5, 60000

    mock_bar_set.__getitem__ = lambda self, sym: [bar1, bar2]
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert "AAPL" in result
    assert len(result["AAPL"]) == 2
    assert result["AAPL"][0]["close"] == 100.5
    assert result["AAPL"][1]["close"] == 101.5
    assert result["AAPL"][0]["timestamp"] == datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)


def test_fetch_bars_history_returns_bars_sorted_by_timestamp():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()

    bar_a = MagicMock()
    bar_a.timestamp = datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc)
    bar_a.open, bar_a.high, bar_a.low, bar_a.close, bar_a.volume = 101.0, 102.0, 100.0, 101.5, 60000

    bar_b = MagicMock()
    bar_b.timestamp = datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc)
    bar_b.open, bar_b.high, bar_b.low, bar_b.close, bar_b.volume = 100.0, 101.0, 99.0, 100.5, 50000

    # SDK returns out-of-order — function must sort
    mock_bar_set.__getitem__ = lambda self, sym: [bar_a, bar_b]
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert result["AAPL"][0]["timestamp"] < result["AAPL"][1]["timestamp"]


def test_fetch_bars_history_omits_symbol_with_no_bars():
    from external.alpaca import fetch_bars_history

    mock_client = MagicMock()
    mock_bar_set = MagicMock()
    mock_bar_set.__getitem__ = lambda self, sym: []
    mock_client.get_stock_bars.return_value = mock_bar_set

    with patch("external.alpaca.StockHistoricalDataClient", return_value=mock_client):
        result = fetch_bars_history(
            symbols=["AAPL"],
            bar_freq="1d",
            start=datetime(2024, 1, 1),
            end=datetime(2024, 1, 4),
            api_key="key",
            secret="secret",
        )

    assert result == {}
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_alpaca_external.py::test_fetch_bars_history_returns_all_bars_in_window tests/test_alpaca_external.py::test_fetch_bars_history_returns_bars_sorted_by_timestamp tests/test_alpaca_external.py::test_fetch_bars_history_omits_symbol_with_no_bars -v
```

Expected: `ImportError` or `AttributeError` — `fetch_bars_history` does not exist yet.

- [ ] **Step 3: Implement `fetch_bars_history` in `external/alpaca.py`**

Add after the existing `fetch_bars` function (around line 72):

```python
def fetch_bars_history(
    symbols: list[str],
    bar_freq: str,
    start: datetime,
    end: datetime,
    api_key: str,
    secret: str,
) -> dict[str, list[dict]]:
    """Fetch all OHLCV bars for symbols in [start, end].

    Returns {symbol: [oldest, ..., newest]} sorted by timestamp.
    Symbols with no bars in the window are omitted from the result.
    """
    client = StockHistoricalDataClient(api_key, secret)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=_timeframe(bar_freq),
        start=start,
        end=end,
    )
    bar_set = client.get_stock_bars(request)
    result = {}
    for symbol in symbols:
        bars = bar_set[symbol]
        if not bars:
            continue
        result[symbol] = sorted(
            [
                {
                    "timestamp": bar.timestamp,
                    "open":      float(bar.open),
                    "high":      float(bar.high),
                    "low":       float(bar.low),
                    "close":     float(bar.close),
                    "volume":    float(bar.volume),
                }
                for bar in bars
            ],
            key=lambda b: b["timestamp"],
        )
    return result
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_alpaca_external.py::test_fetch_bars_history_returns_all_bars_in_window tests/test_alpaca_external.py::test_fetch_bars_history_returns_bars_sorted_by_timestamp tests/test_alpaca_external.py::test_fetch_bars_history_omits_symbol_with_no_bars -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run full external test suite to check for regressions**

```bash
pytest tests/test_alpaca_external.py -v
```

Expected: all existing tests still PASS.

- [ ] **Step 6: Commit**

```bash
git add external/alpaca.py tests/test_alpaca_external.py
git commit -m "feat: add fetch_bars_history to return all bars in a time window"
```

---

### Task 2: `prefill()` on `AlpacaDataHandler`

**Files:**
- Modify: `trading/impl/data_handler/alpaca_data_handler.py`
- Test: `tests/test_alpaca_data_handler.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_alpaca_data_handler.py`:

```python
def test_prefill_populates_deques_with_historical_bars():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from trading.events import TickEvent

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=200,
    )

    fake_history = {
        "AAPL": [
            {
                "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 50000.0,
            },
            {
                "timestamp": datetime(2024, 1, 3, 21, 5, tzinfo=timezone.utc),
                "open": 101.0, "high": 102.0, "low": 100.0, "close": 101.5, "volume": 60000.0,
            },
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 2
    assert bars[0].close == pytest.approx(100.5)
    assert bars[1].close == pytest.approx(101.5)
    assert isinstance(bars[0], TickEvent)


def test_prefill_does_not_emit_events():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    collected = []
    handler = AlpacaDataHandler(
        emit=collected.append,
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    fake_history = {
        "AAPL": [
            {
                "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 50000.0,
            },
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    assert collected == []


def test_prefill_skips_symbol_missing_from_history():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL", "MSFT"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
    )

    # history only has AAPL; MSFT absent
    fake_history = {
        "AAPL": [
            {
                "timestamp": datetime(2024, 1, 2, 21, 5, tzinfo=timezone.utc),
                "open": 100.0, "high": 101.0, "low": 99.0, "close": 100.5, "volume": 50000.0,
            },
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    assert len(handler.get_latest_bars("AAPL", 1)) == 1
    assert handler.get_latest_bars("MSFT", 1) == []


def test_prefill_respects_max_history_deque_limit():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=3,
    )

    # Feed 5 bars into a handler with max_history=3
    fake_history = {
        "AAPL": [
            {"timestamp": datetime(2024, 1, i, 21, 5, tzinfo=timezone.utc),
             "open": float(100 + i), "high": float(101 + i), "low": float(99 + i),
             "close": float(100.5 + i), "volume": 50000.0}
            for i in range(1, 6)
        ]
    }

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        return_value=fake_history,
    ):
        handler.prefill()

    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 3           # capped at max_history
    assert bars[-1].close == pytest.approx(105.5)  # most recent bar retained


def test_prefill_requests_window_of_max_history_times_two_calendar_days():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    from datetime import timedelta

    handler = AlpacaDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        bar_freq="1d",
        api_key="key",
        secret="secret",
        max_history=200,
    )

    calls = []

    def fake_fetch_history(**kwargs):
        calls.append(kwargs)
        return {}

    with patch(
        "trading.impl.data_handler.alpaca_data_handler.fetch_bars_history",
        side_effect=fake_fetch_history,
    ):
        handler.prefill()

    assert len(calls) == 1
    start = calls[0]["start"]
    end   = calls[0]["end"]
    span  = end - start
    assert span >= timedelta(days=400 - 1)   # 200 * 2 calendar days, allow 1 day float
```

Note: the last test (`test_prefill_requests_window_of_max_history_times_two_calendar_days`) uses `side_effect` with keyword arguments — adjust if `fetch_bars_history` is called with positional args (change `**kwargs` to `*args` and inspect `args`). The important assertion is that the time span requested is ≥ `max_history * 2` days.

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_alpaca_data_handler.py::test_prefill_populates_deques_with_historical_bars tests/test_alpaca_data_handler.py::test_prefill_does_not_emit_events tests/test_alpaca_data_handler.py::test_prefill_skips_symbol_missing_from_history tests/test_alpaca_data_handler.py::test_prefill_respects_max_history_deque_limit tests/test_alpaca_data_handler.py::test_prefill_requests_window_of_max_history_times_two_calendar_days -v
```

Expected: `AttributeError` — `prefill` not defined on `AlpacaDataHandler`.

- [ ] **Step 3: Add `fetch_bars_history` import and `prefill()` to `AlpacaDataHandler`**

In `trading/impl/data_handler/alpaca_data_handler.py`:

Change the import line (line 9):
```python
from external.alpaca import fetch_bars, fetch_bars_history
```

Add `prefill()` after `request_shutdown()` (around line 48):

```python
def prefill(self) -> None:
    """Fetch and load historical bars into deques before the live loop starts.

    Requests max_history * 2 calendar days of history so strategies with
    long lookback windows receive correct signals from the first live bar.
    No events are emitted — this is a silent data-load step.
    """
    import logging
    logger = logging.getLogger(__name__)
    now   = datetime.now(tz=ET)
    start = now - timedelta(days=self._max_history * 2)

    history = fetch_bars_history(
        symbols  = self._symbols,
        bar_freq = self._bar_freq,
        start    = start,
        end      = now,
        api_key  = self._api_key,
        secret   = self._secret,
    )

    for symbol in self._symbols:
        raw_bars = history.get(symbol)
        if not raw_bars:
            logger.warning(
                "prefill: no history returned for %s — deque will be empty at startup",
                symbol,
            )
            continue
        for raw in raw_bars:
            tick = TickEvent(
                symbol    = symbol,
                timestamp = raw["timestamp"],
                open      = raw["open"],
                high      = raw["high"],
                low       = raw["low"],
                close     = raw["close"],
                volume    = raw["volume"],
            )
            self._deques[symbol].append(tick)
        logger.info(
            "prefill: loaded %d bars for %s (requested %d)",
            len(self._deques[symbol]),
            symbol,
            self._max_history,
        )
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_alpaca_data_handler.py::test_prefill_populates_deques_with_historical_bars tests/test_alpaca_data_handler.py::test_prefill_does_not_emit_events tests/test_alpaca_data_handler.py::test_prefill_skips_symbol_missing_from_history tests/test_alpaca_data_handler.py::test_prefill_respects_max_history_deque_limit tests/test_alpaca_data_handler.py::test_prefill_requests_window_of_max_history_times_two_calendar_days -v
```

Expected: all 5 PASS.

- [ ] **Step 5: Run full data handler test suite to check for regressions**

```bash
pytest tests/test_alpaca_data_handler.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```bash
git add trading/impl/data_handler/alpaca_data_handler.py tests/test_alpaca_data_handler.py
git commit -m "feat: add AlpacaDataHandler.prefill() to backfill deques at startup"
```

---

### Task 3: Wire `prefill()` into `LiveRunner.run()`

**Files:**
- Modify: `trading/live_runner.py`
- Test: `tests/test_live_runner.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_live_runner.py`:

```python
@pytest.mark.asyncio
async def test_runner_calls_prefill_on_data_handler_if_available():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(return_value=False)
    data.prefill = MagicMock()         # has prefill
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    data.prefill.assert_called_once()


@pytest.mark.asyncio
async def test_runner_prefill_called_after_hydrate_before_first_bar():
    from trading.live_runner import LiveRunner

    call_order = []
    events = queue.Queue()
    data = MagicMock()
    data.update_bars_async = AsyncMock(side_effect=lambda: call_order.append("bar") or False)
    data.prefill = MagicMock(side_effect=lambda: call_order.append("prefill"))
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock(side_effect=lambda p: call_order.append("hydrate"))

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    await runner.run()

    assert call_order.index("hydrate") < call_order.index("prefill")
    assert call_order.index("prefill") < call_order.index("bar")


@pytest.mark.asyncio
async def test_runner_works_without_prefill_method_on_data_handler():
    from trading.live_runner import LiveRunner

    events = queue.Queue()
    data = MagicMock(spec=[                 # spec excludes 'prefill'
        "update_bars_async", "request_shutdown"
    ])
    data.update_bars_async = AsyncMock(return_value=False)
    strategy = MagicMock()
    portfolio = MagicMock()
    execution = MagicMock()
    execution.fill_stream = _null_fill_stream
    reconciler = MagicMock()
    reconciler.hydrate = AsyncMock()

    runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler)
    # Must not raise AttributeError even though data has no .prefill
    await runner.run()
```

- [ ] **Step 2: Run tests to confirm they fail**

```bash
pytest tests/test_live_runner.py::test_runner_calls_prefill_on_data_handler_if_available tests/test_live_runner.py::test_runner_prefill_called_after_hydrate_before_first_bar tests/test_live_runner.py::test_runner_works_without_prefill_method_on_data_handler -v
```

Expected: first two FAIL (prefill not called); third may pass (no crash yet) or fail depending on the mock spec.

- [ ] **Step 3: Add `prefill()` call to `LiveRunner.run()`**

In `trading/live_runner.py`, modify the `run()` method. After line 56 (`await self._reconciler.hydrate(self._portfolio)`) and before the `async with` context manager, add:

```python
        await self._reconciler.hydrate(self._portfolio)

        if hasattr(self._data, "prefill"):
            self._data.prefill()

        async with self._execution.fill_stream() as fill_q:
```

- [ ] **Step 4: Run tests to confirm they pass**

```bash
pytest tests/test_live_runner.py::test_runner_calls_prefill_on_data_handler_if_available tests/test_live_runner.py::test_runner_prefill_called_after_hydrate_before_first_bar tests/test_live_runner.py::test_runner_works_without_prefill_method_on_data_handler -v
```

Expected: all 3 PASS.

- [ ] **Step 5: Run full live runner test suite to check for regressions**

```bash
pytest tests/test_live_runner.py -v
```

Expected: all tests PASS.

- [ ] **Step 6: Run the full test suite**

```bash
pytest -v
```

Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add trading/live_runner.py tests/test_live_runner.py
git commit -m "feat: call data.prefill() at startup in LiveRunner to warm up history deques"
```

---

## Self-Review

**Spec coverage:**

| Requirement | Task covering it |
|---|---|
| `fetch_bars` only returns last bar | Task 1: new `fetch_bars_history` returns all bars |
| Deques start empty | Task 2: `prefill()` fills deques before loop |
| Fetch window too narrow (3 days / 60 min) | Task 2: window = `max_history * 2` calendar days |
| Only `bars[-1]` appended per call | Task 2: all bars from history appended in order |
| No backfill on startup | Task 3: `LiveRunner` calls `prefill()` after reconcile |
| Strategies fire on insufficient history | Fixed end-to-end by Tasks 1+2+3 |

**Placeholder scan:** No TBDs, no "similar to Task N" references, all code blocks complete.

**Type consistency:**
- `fetch_bars_history` returns `dict[str, list[dict]]` — matches what `prefill()` iterates over (`history.get(symbol)` → `list[dict]`).
- `TickEvent` constructor arguments in `prefill()` match the existing pattern in `update_bars_async`.
- `fetch_bars_history` import in `alpaca_data_handler.py` matches the function name added in Task 1.
- `hasattr(self._data, "prefill")` guard in `LiveRunner` means no ABC change needed.
