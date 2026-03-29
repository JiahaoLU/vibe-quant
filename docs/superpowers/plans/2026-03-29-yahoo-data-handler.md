# Yahoo Finance Data Handler Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add `YahooDataHandler` that fetches historical daily bars from Yahoo Finance and replays them through the backtester, with `yfinance` isolated in `external/yahoo.py`.

**Architecture:** `external/yahoo.py` wraps `yfinance` and exposes `fetch_daily_bars(symbol, start, end) -> list[dict]`. `YahooDataHandler` in `trading/impl/` accepts `fetch` as an injected callable — keeping the engine free of external imports. `run_backtest.py` wires them together.

**Tech Stack:** Python 3.10+, `yfinance>=0.2`, `pytest`, `unittest.mock`

---

### Task 1: Add yfinance dependency and scaffold `external/` package

**Files:**
- Modify: `requirements.txt`
- Create: `external/__init__.py`

- [ ] **Step 1: Add yfinance to requirements.txt**

Open `requirements.txt` and add after the existing `# Core engine` comment block:

```
# External data sources (outside the core engine):
yfinance>=0.2
```

Full file after edit:
```
# Core engine — no third-party dependencies required.

# Visualization (plot_results.ipynb):
matplotlib>=3.7

# Jupyter kernel registration:
ipykernel

# Tests:
pytest>=7.0

# External data sources (outside the core engine):
yfinance>=0.2

# Optional — makes post-run analysis cleaner (not used yet):
# pandas>=2.0
```

- [ ] **Step 2: Create `external/__init__.py`**

Create an empty file at `external/__init__.py`:
```python
```

- [ ] **Step 3: Install the new dependency**

```bash
pip install -r requirements.txt
```

Expected: yfinance and its dependencies (pandas, requests, etc.) install without error.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt external/__init__.py
git commit -m "feat: scaffold external/ package and add yfinance dependency"
```

---

### Task 2: Implement `external/yahoo.py` with TDD

**Files:**
- Create: `external/yahoo.py`
- Create: `tests/test_yahoo_data_handler.py` (fetch tests only in this task)

- [ ] **Step 1: Write the failing fetch test**

Create `tests/test_yahoo_data_handler.py`:

```python
import queue
from datetime import datetime
from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from external.yahoo import fetch_daily_bars


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_history_df(rows: list[dict]) -> pd.DataFrame:
    """Build a DataFrame that mirrors what yfinance Ticker.history() returns."""
    index = pd.DatetimeIndex(
        [pd.Timestamp(r["timestamp"], tz="UTC") for r in rows]
    )
    return pd.DataFrame(
        {
            "Open":   [r["open"]   for r in rows],
            "High":   [r["high"]   for r in rows],
            "Low":    [r["low"]    for r in rows],
            "Close":  [r["close"]  for r in rows],
            "Volume": [r["volume"] for r in rows],
        },
        index=index,
    )


AAPL_ROWS = [
    {"timestamp": "2020-01-02", "open": 100.0, "high": 101.0, "low": 99.0,  "close": 100.5, "volume": 1_000.0},
    {"timestamp": "2020-01-03", "open": 100.5, "high": 102.0, "low": 100.0, "close": 101.0, "volume": 1_100.0},
]
MSFT_ROWS = [
    {"timestamp": "2020-01-02", "open": 200.0, "high": 201.0, "low": 199.0, "close": 200.5, "volume": 2_000.0},
    {"timestamp": "2020-01-04", "open": 200.5, "high": 202.0, "low": 200.0, "close": 201.0, "volume": 2_100.0},
]


# ---------------------------------------------------------------------------
# fetch_daily_bars tests
# ---------------------------------------------------------------------------

def test_fetch_daily_bars_returns_list_of_dicts():
    df = _make_history_df(AAPL_ROWS)
    with patch("external.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = df
        result = fetch_daily_bars("AAPL", "2020-01-01", "2020-01-04")

    assert len(result) == 2
    assert result[0]["timestamp"] == datetime(2020, 1, 2)
    assert result[0]["open"]      == 100.0
    assert result[0]["high"]      == 101.0
    assert result[0]["low"]       == 99.0
    assert result[0]["close"]     == 100.5
    assert result[0]["volume"]    == 1_000.0


def test_fetch_daily_bars_raises_on_empty_response():
    empty_df = pd.DataFrame()
    with patch("external.yahoo.yf.Ticker") as mock_ticker_cls:
        mock_ticker_cls.return_value.history.return_value = empty_df
        with pytest.raises(ValueError, match="AAPL"):
            fetch_daily_bars("AAPL", "2020-01-01", "2020-01-04")
```

- [ ] **Step 2: Run to confirm it fails**

```bash
pytest tests/test_yahoo_data_handler.py::test_fetch_daily_bars_returns_list_of_dicts tests/test_yahoo_data_handler.py::test_fetch_daily_bars_raises_on_empty_response -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'external.yahoo'`

- [ ] **Step 3: Implement `external/yahoo.py`**

Create `external/yahoo.py`:

```python
from datetime import datetime

import yfinance as yf


def fetch_daily_bars(symbol: str, start: str, end: str) -> list[dict]:
    """
    Fetch daily OHLCV bars for a symbol from Yahoo Finance.

    Parameters
    ----------
    symbol : str  ticker symbol, e.g. "AAPL"
    start  : str  ISO date string, inclusive, e.g. "2020-01-01"
    end    : str  ISO date string, exclusive, e.g. "2022-01-01"

    Returns
    -------
    list[dict]  each dict: timestamp (datetime), open, high, low, close, volume (float)

    Raises
    ------
    ValueError  if the ticker is unknown or the date range returns no data
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end)
    if df.empty:
        raise ValueError(
            f"No data returned for symbol '{symbol}' between {start} and {end}. "
            "The ticker may be invalid or the date range may produce no results."
        )
    result: list[dict] = []
    for ts, row in df.iterrows():
        result.append({
            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
            "open":      float(row["Open"]),
            "high":      float(row["High"]),
            "low":       float(row["Low"]),
            "close":     float(row["Close"]),
            "volume":    float(row["Volume"]),
        })
    return result
```

- [ ] **Step 4: Run to confirm tests pass**

```bash
pytest tests/test_yahoo_data_handler.py::test_fetch_daily_bars_returns_list_of_dicts tests/test_yahoo_data_handler.py::test_fetch_daily_bars_raises_on_empty_response -v
```

Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add external/yahoo.py tests/test_yahoo_data_handler.py
git commit -m "feat: add external/yahoo.py with fetch_daily_bars"
```

---

### Task 3: Implement `YahooDataHandler` with TDD

**Files:**
- Create: `trading/impl/yahoo_data_handler.py`
- Modify: `tests/test_yahoo_data_handler.py` (append handler tests)

- [ ] **Step 1: Append failing handler tests to `tests/test_yahoo_data_handler.py`**

Add the following at the bottom of the existing `tests/test_yahoo_data_handler.py` (after the fetch tests):

```python
from trading.impl.yahoo_data_handler import YahooDataHandler
from trading.events import BarBundleEvent, EventType


# ---------------------------------------------------------------------------
# YahooDataHandler helpers
# ---------------------------------------------------------------------------

def _make_fetch(data: dict[str, list[dict]]):
    """Return a fetch callable that serves pre-canned rows, or raises on unknown symbol."""
    def fetch(symbol: str, start: str, end: str) -> list[dict]:
        if symbol not in data or not data[symbol]:
            raise ValueError(f"No data for {symbol}")
        return data[symbol]
    return fetch


# ---------------------------------------------------------------------------
# YahooDataHandler tests
# ---------------------------------------------------------------------------

def test_handler_update_bars_emits_bar_bundle_event():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    assert handler.update_bars() is True
    assert len(collected) == 1
    assert isinstance(collected[0], BarBundleEvent)
    assert collected[0].type == EventType.BAR_BUNDLE
    assert "AAPL" in collected[0].bars
    assert "MSFT" in collected[0].bars


def test_handler_timeline_is_union_of_symbol_timestamps():
    # AAPL: Jan 2, Jan 3 — MSFT: Jan 2, Jan 4 → union: Jan 2, Jan 3, Jan 4
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    count = 0
    while handler.update_bars():
        count += 1
    assert count == 3


def test_handler_missing_bar_is_zero_filled():
    # On Jan 3 MSFT has no bar — should be zero-filled
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2 — both present
    handler.update_bars()  # Jan 3 — MSFT missing
    bundle = collected[1]
    assert bundle.bars["AAPL"].close == 101.0
    assert bundle.bars["MSFT"].close == 0.0


def test_handler_get_latest_bars_returns_history():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # Jan 2
    handler.update_bars()  # Jan 3
    bars = handler.get_latest_bars("AAPL", 2)
    assert len(bars) == 2
    assert bars[-1].close == 101.0
    assert bars[0].close  == 100.5


def test_handler_get_latest_bars_partial_history():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    handler.update_bars()  # only 1 bar so far
    bars = handler.get_latest_bars("AAPL", 10)
    assert len(bars) == 1


def test_handler_update_bars_returns_false_when_exhausted():
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    while handler.update_bars():
        pass
    assert handler.update_bars() is False


def test_handler_raises_on_unknown_symbol():
    fetch = _make_fetch({})  # returns nothing for any symbol
    with pytest.raises(ValueError):
        YahooDataHandler([].append, ["INVALID"], "2020-01-01", "2020-01-05", fetch=fetch)
```

- [ ] **Step 2: Run to confirm tests fail**

```bash
pytest tests/test_yahoo_data_handler.py -k "handler" -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trading.impl.yahoo_data_handler'`

- [ ] **Step 3: Implement `trading/impl/yahoo_data_handler.py`**

Create `trading/impl/yahoo_data_handler.py`:

```python
from collections import deque
from datetime import datetime
from typing import Callable

from ..base.data import DataHandler
from ..events import BarBundleEvent, Event, TickEvent


class YahooDataHandler(DataHandler):
    """
    Fetches historical daily bars via an injected fetch callable at construction,
    then replays them one BarBundleEvent per timestep.

    Parameters
    ----------
    emit        : event queue put method
    symbols     : list of ticker symbols, e.g. ["AAPL", "MSFT"]
    start       : ISO date string, inclusive, e.g. "2020-01-01"
    end         : ISO date string, exclusive, e.g. "2022-01-01"
    fetch       : callable(symbol, start, end) -> list[dict] with keys
                  timestamp, open, high, low, close, volume
    max_history : maximum bar history kept per symbol
    """

    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        start:       str,
        end:         str,
        fetch:       Callable[[str, str, str], list[dict]],
        max_history: int = 200,
    ):
        super().__init__(emit)
        self._symbols = symbols

        raw: dict[str, dict[datetime, TickEvent]] = {}
        for symbol in symbols:
            rows = fetch(symbol, start, end)
            raw[symbol] = {
                row["timestamp"]: TickEvent(
                    symbol    = symbol,
                    timestamp = row["timestamp"],
                    open      = row["open"],
                    high      = row["high"],
                    low       = row["low"],
                    close     = row["close"],
                    volume    = row["volume"],
                )
                for row in rows
            }

        all_ts: set[datetime] = set()
        for data in raw.values():
            all_ts.update(data.keys())
        timeline = sorted(all_ts)

        self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
        for ts in timeline:
            bundle = {
                symbol: raw[symbol].get(
                    ts,
                    TickEvent(symbol=symbol, timestamp=ts, open=0.0, high=0.0, low=0.0, close=0.0, volume=0.0),
                )
                for symbol in symbols
            }
            self._merged.append((ts, bundle))

        self._index = 0
        self._history: dict[str, deque] = {s: deque(maxlen=max_history) for s in symbols}

    def update_bars(self) -> bool:
        if self._index >= len(self._merged):
            return False
        ts, bars = self._merged[self._index]
        self._index += 1
        for symbol, bar in bars.items():
            self._history[symbol].append(bar)
        self._emit(BarBundleEvent(timestamp=ts, bars=bars))
        return True

    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]:
        bars = list(self._history[symbol])
        return bars[-n:] if len(bars) >= n else bars
```

- [ ] **Step 4: Run to confirm handler tests pass**

```bash
pytest tests/test_yahoo_data_handler.py -v
```

Expected: all tests pass

- [ ] **Step 5: Commit**

```bash
git add trading/impl/yahoo_data_handler.py tests/test_yahoo_data_handler.py
git commit -m "feat: add YahooDataHandler with injected fetch callable"
```

---

### Task 4: Export `YahooDataHandler` and update `run_backtest.py`

**Files:**
- Modify: `trading/impl/__init__.py`
- Modify: `run_backtest.py`

- [ ] **Step 1: Export from `trading/impl/__init__.py`**

Current `trading/impl/__init__.py`:
```python
from .multi_csv_data_handler      import MultiCSVDataHandler
from .simulated_execution_handler import SimulatedExecutionHandler
from .simple_portfolio            import SimplePortfolio
from .sma_crossover_strategy      import SMACrossoverStrategy
from .strategy_container          import StrategyContainer

__all__ = [
    "MultiCSVDataHandler",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "SMACrossoverStrategy",
    "StrategyContainer",
]
```

Add `YahooDataHandler`:
```python
from .multi_csv_data_handler      import MultiCSVDataHandler
from .simulated_execution_handler import SimulatedExecutionHandler
from .simple_portfolio            import SimplePortfolio
from .sma_crossover_strategy      import SMACrossoverStrategy
from .strategy_container          import StrategyContainer
from .yahoo_data_handler          import YahooDataHandler

__all__ = [
    "MultiCSVDataHandler",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "SMACrossoverStrategy",
    "StrategyContainer",
    "YahooDataHandler",
]
```

- [ ] **Step 2: Update `run_backtest.py` to use `YahooDataHandler`**

Replace the current `run_backtest.py` content with:

```python
"""
Entry point — wire all components together and run the backtest.
Modify SYMBOLS, START, END, INITIAL_CAPITAL, FAST_WINDOW, SLOW_WINDOW,
COMMISSION, SLIPPAGE_PCT to experiment.
"""
import csv
import queue

from external.yahoo import fetch_daily_bars
from trading.backtester import Backtester
from trading.impl import (
    SimulatedExecutionHandler,
    SimplePortfolio,
    SMACrossoverStrategy,
    StrategyContainer,
    YahooDataHandler,
)

# --- Configuration -----------------------------------------------------------
SYMBOLS         = ["AAPL", "MSFT"]
START           = "2020-01-01"
END             = "2022-01-01"
INITIAL_CAPITAL = 10_000.0
FAST_WINDOW     = 10
SLOW_WINDOW     = 30
COMMISSION      = 1.0    # dollars per trade
SLIPPAGE_PCT    = 0.0005 # 0.05%
RESULTS_PATH    = "results/equity_curve.csv"
# -----------------------------------------------------------------------------

events   = queue.Queue()
data     = None  # resolved after strategy symbols are known

strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
strategy.add(SMACrossoverStrategy, symbols=SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW)

symbols   = strategy.symbols
data      = YahooDataHandler(events.put, symbols, start=START, end=END, fetch=fetch_daily_bars)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, symbols, initial_capital=INITIAL_CAPITAL)
execution = SimulatedExecutionHandler(events.put, commission=COMMISSION, slippage_pct=SLIPPAGE_PCT)

bt = Backtester(events, data, strategy, portfolio, execution)
bt.run()

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
```

- [ ] **Step 3: Run full test suite to confirm nothing broke**

```bash
pytest tests/ -v
```

Expected: all existing tests pass (no network calls — `YahooDataHandler` is not tested by the existing suite)

- [ ] **Step 4: Commit**

```bash
git add trading/impl/__init__.py run_backtest.py
git commit -m "feat: wire YahooDataHandler into run_backtest.py"
```

---

### Task 5: Register `integration` marker and add integration test

**Files:**
- Create: `conftest.py`
- Create: `tests/test_yahoo_external.py`

- [ ] **Step 1: Create `conftest.py` at project root**

```python
import pytest


def pytest_configure(config):
    config.addinivalue_line(
        "markers",
        "integration: mark test as requiring live network access (run with: pytest -m integration)",
    )
```

- [ ] **Step 2: Create `tests/test_yahoo_external.py`**

```python
import pytest
from datetime import datetime

from external.yahoo import fetch_daily_bars


@pytest.mark.integration
def test_fetch_daily_bars_real_network():
    """Fetch a short date range for a known ticker. Requires internet access."""
    rows = fetch_daily_bars("AAPL", "2023-01-01", "2023-01-15")
    assert len(rows) > 0
    row = rows[0]
    assert isinstance(row["timestamp"], datetime)
    assert row["open"]   > 0
    assert row["high"]   >= row["open"]
    assert row["low"]    <= row["open"]
    assert row["close"]  > 0
    assert row["volume"] > 0


@pytest.mark.integration
def test_fetch_daily_bars_invalid_ticker_raises():
    """An invalid ticker should raise ValueError."""
    with pytest.raises(ValueError, match="INVALID_TICKER_XYZ"):
        fetch_daily_bars("INVALID_TICKER_XYZ", "2023-01-01", "2023-01-15")
```

- [ ] **Step 3: Confirm integration tests are skipped by default**

```bash
pytest tests/ -v
```

Expected: all existing tests pass, integration tests do not appear (they are not collected without `-m integration`)

- [ ] **Step 4: Run integration tests explicitly (requires network)**

```bash
pytest -m integration -v
```

Expected: 2 passed (with live network access)

- [ ] **Step 5: Commit**

```bash
git add conftest.py tests/test_yahoo_external.py
git commit -m "test: add integration tests for external/yahoo.py; register integration marker"
```
