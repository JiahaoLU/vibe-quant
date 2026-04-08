# Survivorship-Bias-Free Universe Builder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add point-in-time universe gating to the backtester so delisted symbols are included and force-exited at their exit date, eliminating survivorship bias.

**Architecture:** An `IndexConstituentsUniverseBuilder` reads a cached `data/universe_manifest.csv` (populated by `external/index_constituents.py`) and exposes an `is_active(symbol, ts)` method that is injected into `YahooDataHandler` and `MultiCSVDataHandler`. Those handlers mark the exit-transition bar as `is_delisted=True`; `SimplePortfolio` detects this flag and force-closes the position before processing any signals.

**Tech Stack:** Python stdlib only throughout (`urllib.request`, `csv`, `io`); data sourced from [yfiua/index-constituents](https://github.com/yfiua/index-constituents) monthly snapshot CSVs via GitHub Pages — no API key, no new PyPI dependency; `pytest` for tests.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Modify | `trading/events.py` | Add `is_delisted: bool = False` to `TickEvent` |
| Create | `trading/base/universe_builder.py` | ABC: `is_active`, `exit_date`, `all_symbols` |
| Modify | `trading/base/__init__.py` | Export `UniverseBuilder` |
| Create | `trading/impl/index_constituents_universe_builder.py` | Read manifest CSV, implement ABC |
| Modify | `trading/impl/__init__.py` | Export `IndexConstituentsUniverseBuilder` |
| Create | `external/index_constituents.py` | Fetch monthly snapshots from yfiua/index-constituents, build manifest CSV |
| Modify | `trading/impl/yahoo_data_handler.py` | Accept `universe_builder`, gate `_merged` loop |
| Modify | `trading/impl/multi_csv_data_handler.py` | Same injection pattern as Yahoo handler |
| Modify | `trading/impl/simple_portfolio.py` | Force-exit pre-pass on `is_delisted` bars |
| Modify | `run_backtest.py` | `USE_UNIVERSE_GATING`, `INDEX_CODE`, `RELOAD_UNIVERSE` config + wiring |
| Modify | `requirements.txt` | No new dependency — `urllib.request` is stdlib |
| Create | `tests/test_index_constituents_universe_builder.py` | Unit tests for builder logic |
| Modify | `tests/test_events.py` | Two tests for the new `is_delisted` field |
| Modify | `tests/test_yahoo_data_handler.py` | Tests for `is_delisted` marking and exclusion |
| Modify | `tests/test_data.py` | Tests for `is_delisted` in `MultiCSVDataHandler` |
| Modify | `tests/test_portfolio.py` | Tests for force-exit on `is_delisted` bars |
| Create | `tests/test_index_constituents_external.py` | Tests for `external/index_constituents.py` with mocked HTTP |

---

## Task 1: Add `is_delisted` to `TickEvent`

**Files:**
- Modify: `trading/events.py:28`
- Modify: `tests/test_events.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_events.py`:

```python
def test_tick_event_is_delisted_defaults_to_false():
    ts = datetime(2020, 1, 2)
    bar = TickEvent(symbol="AAPL", timestamp=ts, open=100.0, high=101.0, low=99.0, close=100.5, volume=1000.0)
    assert bar.is_delisted is False


def test_tick_event_is_delisted_can_be_set_true():
    ts = datetime(2020, 1, 2)
    bar = TickEvent(symbol="ENRN", timestamp=ts, open=1.0, high=1.0, low=0.5, close=0.8, volume=500.0, is_delisted=True)
    assert bar.is_delisted is True
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_events.py::test_tick_event_is_delisted_defaults_to_false tests/test_events.py::test_tick_event_is_delisted_can_be_set_true -v
```

Expected: FAIL — `TickEvent() got unexpected keyword argument 'is_delisted'`

- [ ] **Step 3: Add the field**

In `trading/events.py`, add `is_delisted: bool = False` after `is_synthetic: bool = False` (line 28):

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
    is_delisted:  bool = False   # True on the last bar before the symbol exits the universe
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_events.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/events.py tests/test_events.py
git commit -m "feat: add is_delisted flag to TickEvent"
```

---

## Task 2: `UniverseBuilder` ABC + base exports

**Files:**
- Create: `trading/base/universe_builder.py`
- Modify: `trading/base/__init__.py`

- [ ] **Step 1: Create the ABC**

Create `trading/base/universe_builder.py`:

```python
from abc import ABC, abstractmethod
from datetime import datetime


class UniverseBuilder(ABC):
    @abstractmethod
    def is_active(self, symbol: str, timestamp: datetime) -> bool:
        """True if symbol was in the universe at timestamp."""

    @abstractmethod
    def exit_date(self, symbol: str) -> datetime | None:
        """The date the symbol exited the universe, or None if still active."""

    @abstractmethod
    def all_symbols(self) -> list[str]:
        """All symbols ever in the universe (including delisted)."""
```

- [ ] **Step 2: Export from `trading/base/__init__.py`**

Add `from .universe_builder import UniverseBuilder` and add `"UniverseBuilder"` to `__all__`:

```python
from .data          import DataHandler
from .execution     import ExecutionHandler
from .portfolio     import Portfolio
from .result_writer import BacktestResultWriter
from .strategy      import Strategy, StrategyBase, StrategySignalGenerator
from .strategy_params import StrategyParams
from .strategy_params_loader import StrategyParamsLoader
from .universe_builder import UniverseBuilder

__all__ = [
    "BacktestResultWriter",
    "DataHandler",
    "ExecutionHandler",
    "Portfolio",
    "Strategy",
    "StrategyBase",
    "StrategySignalGenerator",
    "StrategyParams",
    "StrategyParamsLoader",
    "UniverseBuilder",
]
```

- [ ] **Step 3: Verify import works**

```
python -c "from trading.base import UniverseBuilder; print('ok')"
```

Expected: `ok`

- [ ] **Step 4: Commit**

```bash
git add trading/base/universe_builder.py trading/base/__init__.py
git commit -m "feat: add UniverseBuilder ABC"
```

---

## Task 3: `IndexConstituentsUniverseBuilder` + tests + impl exports

**Files:**
- Create: `trading/impl/index_constituents_universe_builder.py`
- Create: `tests/test_index_constituents_universe_builder.py`
- Modify: `trading/impl/__init__.py`

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index_constituents_universe_builder.py`:

```python
import csv
import os
import tempfile
from datetime import datetime

import pytest

from trading.impl.index_constituents_universe_builder import IndexConstituentsUniverseBuilder


def _make_manifest(rows: list[dict]) -> str:
    f = tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="")
    writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
    writer.writeheader()
    writer.writerows(rows)
    f.close()
    return f.name


MANIFEST_ROWS = [
    {"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""},
    {"symbol": "ENRN", "enter_date": "2000-01-01", "exit_date": "2001-12-02"},
    {"symbol": "MSFT", "enter_date": "2021-01-01", "exit_date": ""},
]


def test_is_active_returns_true_within_window():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("AAPL", datetime(2020, 6, 1)) is True
    finally:
        os.unlink(path)


def test_is_active_returns_false_before_enter_date():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("MSFT", datetime(2020, 6, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_false_on_exit_date():
    # exit_date is exclusive — the symbol is already gone on that date
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2001, 12, 2)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_true_day_before_exit():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2001, 12, 1)) is True
    finally:
        os.unlink(path)


def test_is_active_returns_false_after_exit_date():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("ENRN", datetime(2002, 1, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_returns_false_for_unknown_symbol():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("LEHM", datetime(2020, 1, 1)) is False
    finally:
        os.unlink(path)


def test_is_active_no_exit_date_stays_active_far_future():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).is_active("AAPL", datetime(2099, 1, 1)) is True
    finally:
        os.unlink(path)


def test_exit_date_returns_none_for_open_ended():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).exit_date("AAPL") is None
    finally:
        os.unlink(path)


def test_exit_date_returns_datetime_for_delisted():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).exit_date("ENRN") == datetime(2001, 12, 2)
    finally:
        os.unlink(path)


def test_exit_date_returns_none_for_unknown_symbol():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert IndexConstituentsUniverseBuilder(path).exit_date("UNKNOWN") is None
    finally:
        os.unlink(path)


def test_all_symbols_returns_all_rows():
    path = _make_manifest(MANIFEST_ROWS)
    try:
        assert set(IndexConstituentsUniverseBuilder(path).all_symbols()) == {"AAPL", "ENRN", "MSFT"}
    finally:
        os.unlink(path)
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_index_constituents_universe_builder.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'trading.impl.index_constituents_universe_builder'`

- [ ] **Step 3: Create the implementation**

Create `trading/impl/index_constituents_universe_builder.py`:

```python
import csv
from datetime import datetime

from ..base.universe_builder import UniverseBuilder


class IndexConstituentsUniverseBuilder(UniverseBuilder):
    _DATE_FMT = "%Y-%m-%d"

    def __init__(self, manifest_path: str):
        self._universe: dict[str, tuple[datetime, datetime | None]] = {}
        with open(manifest_path, newline="") as f:
            for row in csv.DictReader(f):
                enter = datetime.strptime(row["enter_date"], self._DATE_FMT)
                exit_ = (
                    datetime.strptime(row["exit_date"], self._DATE_FMT)
                    if row["exit_date"].strip()
                    else None
                )
                self._universe[row["symbol"]] = (enter, exit_)

    def is_active(self, symbol: str, timestamp: datetime) -> bool:
        if symbol not in self._universe:
            return False
        enter, exit_ = self._universe[symbol]
        return enter <= timestamp and (exit_ is None or timestamp < exit_)

    def exit_date(self, symbol: str) -> datetime | None:
        if symbol not in self._universe:
            return None
        return self._universe[symbol][1]

    def all_symbols(self) -> list[str]:
        return list(self._universe.keys())
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_index_constituents_universe_builder.py -v
```

Expected: all PASS

- [ ] **Step 5: Export from `trading/impl/__init__.py`**

```python
from .json_strategy_params_loader import JsonStrategyParamsLoader
from .multi_csv_data_handler import MultiCSVDataHandler
from .simulated_execution_handler import SimulatedExecutionHandler
from .simple_portfolio       import SimplePortfolio
from .strategy_container import StrategyContainer
from .index_constituents_universe_builder import IndexConstituentsUniverseBuilder
from .yahoo_data_handler import YahooDataHandler

__all__ = [
    "JsonStrategyParamsLoader",
    "MultiCSVDataHandler",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "StrategyContainer",
    "IndexConstituentsUniverseBuilder",
    "YahooDataHandler",
]
```

- [ ] **Step 6: Commit**

```bash
git add trading/impl/index_constituents_universe_builder.py trading/impl/__init__.py tests/test_index_constituents_universe_builder.py
git commit -m "feat: add IndexConstituentsUniverseBuilder with point-in-time is_active gating"
```

---

## Task 4: `external/index_constituents.py` — manifest fetch and cache

**Files:**
- Create: `external/index_constituents.py`
- Create: `tests/test_index_constituents_external.py`

Data source: [yfiua/index-constituents](https://github.com/yfiua/index-constituents) publishes monthly point-in-time snapshots at:
`https://yfiua.github.io/index-constituents/YYYY/MM/constituents-{index_code}.csv`

Each snapshot is a CSV with `Symbol,Name` columns. We fetch every month in `[start, end]`, track when each symbol first appears (`enter_date`) and when it last appeared (`exit_date` = month after last seen).

Supported index codes include: `sp500`, `nasdaq100`, `csi300`, `csi500`. No API key required.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_index_constituents_external.py`:

```python
import csv
import os
import tempfile
from unittest.mock import patch, MagicMock

import pytest

from external.index_constituents import fetch_universe_manifest, load_or_fetch_universe_manifest


def _mock_urlopen(responses: dict[str, str]):
    """
    responses: {url_substring: csv_text}
    Returns a context-manager mock that serves CSV by matching url substring.
    """
    def side_effect(url):
        for key, content in responses.items():
            if key in url:
                mock_resp = MagicMock()
                mock_resp.read.return_value = content.encode()
                mock_resp.__enter__ = lambda s: s
                mock_resp.__exit__ = MagicMock(return_value=False)
                return mock_resp
        raise Exception(f"404 Not Found: {url}")
    return side_effect


# Two snapshots: Jan 2020 has AAPL+ENRN; Feb 2020 ENRN is gone
JAN_CSV = "Symbol,Name\nAAPL,Apple\nENRN,Enron\n"
FEB_CSV = "Symbol,Name\nAAPL,Apple\n"


def test_fetch_saves_manifest_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "manifest.csv")
        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)):
            result_path = fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", output_path=out)

        assert result_path == out
        assert os.path.exists(out)
        with open(out, newline="") as f:
            rows = {r["symbol"]: r for r in csv.DictReader(f)}
        assert rows["AAPL"]["enter_date"] == "2020-01-01"
        assert rows["AAPL"]["exit_date"] == ""          # still active at end
        assert rows["ENRN"]["enter_date"] == "2020-01-01"
        assert rows["ENRN"]["exit_date"] == "2020-03-01"  # next month after last seen (Feb)


def test_fetch_skips_missing_months_gracefully():
    """If a monthly snapshot 404s, it is skipped without crashing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "manifest.csv")
        # Only Jan exists; Feb raises
        responses = {"2020/01": JAN_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)):
            result_path = fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", output_path=out)
        with open(out, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2


def test_fetch_raises_on_no_data():
    """Raises ValueError if no months could be fetched at all."""
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "manifest.csv")
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen({})):
            with pytest.raises(ValueError, match="No constituent data"):
                fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", output_path=out)


def test_load_or_fetch_skips_http_when_file_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "manifest.csv")
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            w.writeheader()
            w.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        with patch("external.index_constituents.urllib.request.urlopen") as mock_open:
            result = load_or_fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", output_path=out, reload=False)
            mock_open.assert_not_called()

        assert result == out


def test_load_or_fetch_refetches_when_reload_true():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "manifest.csv")
        with open(out, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            w.writeheader()
            w.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)):
            load_or_fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", output_path=out, reload=True)
        # File should now have both AAPL and ENRN
        with open(out, newline="") as f:
            symbols = {r["symbol"] for r in csv.DictReader(f)}
        assert symbols == {"AAPL", "ENRN"}
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_index_constituents_external.py -v
```

Expected: FAIL — `ModuleNotFoundError: No module named 'external.index_constituents'`

- [ ] **Step 3: Create the implementation**

Create `external/index_constituents.py`:

```python
import csv
import io
import os
import urllib.request
from datetime import datetime


_BASE_URL = "https://yfiua.github.io/index-constituents"


def _iter_months(start_dt: datetime, end_dt: datetime):
    """Yield (year, month) tuples for every month in [start_dt, end_dt]."""
    y, m = start_dt.year, start_dt.month
    while (y, m) <= (end_dt.year, end_dt.month):
        yield y, m
        m += 1
        if m > 12:
            m, y = 1, y + 1


def _next_month_date(year: int, month: int) -> str:
    """Return the first day of the month following (year, month) as YYYY-MM-DD."""
    m = month + 1
    y = year
    if m > 12:
        m, y = 1, y + 1
    return f"{y:04d}-{m:02d}-01"


def fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
    output_path: str = "data/universe_manifest.csv",
) -> str:
    """
    Build a universe manifest CSV by fetching monthly constituent snapshots from
    https://yfiua.github.io/index-constituents/YYYY/MM/constituents-{index_code}.csv

    For each symbol, records:
      enter_date — first month it appeared (YYYY-MM-01)
      exit_date  — first month it was absent after being present (YYYY-MM-01),
                   or "" if still active at end.

    Months that return a non-200 response are skipped silently.
    Raises ValueError if no months could be fetched at all.
    """
    start_dt = datetime.fromisoformat(start)
    end_dt   = datetime.fromisoformat(end)

    # symbol -> {"enter": (y, m), "last_seen": (y, m)}
    history: dict[str, dict] = {}
    end_ym = (end_dt.year, end_dt.month)

    for year, month in _iter_months(start_dt, end_dt):
        url = f"{_BASE_URL}/{year:04d}/{month:02d}/constituents-{index_code}.csv"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode()
        except Exception:
            continue  # snapshot not available for this month — skip

        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            symbol = row["Symbol"]
            if symbol not in history:
                history[symbol] = {"enter": (year, month), "last_seen": (year, month)}
            else:
                history[symbol]["last_seen"] = (year, month)

    if not history:
        raise ValueError(
            f"No constituent data found for index '{index_code}' in [{start}, {end}]."
        )

    rows = []
    for symbol, info in sorted(history.items()):
        enter_y, enter_m = info["enter"]
        last_y,  last_m  = info["last_seen"]
        enter_date = f"{enter_y:04d}-{enter_m:02d}-01"
        exit_date  = _next_month_date(last_y, last_m) if (last_y, last_m) < end_ym else ""
        rows.append({"symbol": symbol, "enter_date": enter_date, "exit_date": exit_date})

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def load_or_fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
    output_path: str = "data/universe_manifest.csv",
    reload: bool = False,
) -> str:
    """
    Return path to the manifest CSV.
    Uses the cached file if reload=False and the file already exists.
    Otherwise calls fetch_universe_manifest.
    """
    if not reload and os.path.exists(output_path):
        return output_path
    return fetch_universe_manifest(index_code, start, end, output_path)
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_index_constituents_external.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add external/index_constituents.py tests/test_index_constituents_external.py
git commit -m "feat: add index-constituents universe manifest builder with monthly snapshot fetch"
```

---

## Task 5: `YahooDataHandler` — universe_builder injection

**Files:**
- Modify: `trading/impl/yahoo_data_handler.py`
- Modify: `tests/test_yahoo_data_handler.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_yahoo_data_handler.py`:

```python
from unittest.mock import MagicMock
from trading.base.universe_builder import UniverseBuilder


def _make_universe_builder(active_until: dict[str, datetime]):
    """
    Returns a mock UniverseBuilder.
    active_until: symbol -> last active datetime (exclusive exit boundary).
    If symbol not in dict, always active.
    """
    builder = MagicMock(spec=UniverseBuilder)
    def is_active(symbol, timestamp):
        if symbol not in active_until:
            return True
        return timestamp < active_until[symbol]
    builder.is_active.side_effect = is_active
    return builder


def test_handler_marks_exit_bar_as_delisted():
    """The bar at the exit timestamp is emitted once with is_delisted=True."""
    # AAPL exits after Jan 2 (i.e., Jan 3 bar is the delisted bar)
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    ub = _make_universe_builder({"AAPL": datetime(2020, 1, 3)})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch, universe_builder=ub)

    handler.update_bars()  # Jan 2 — AAPL active
    bundle_jan2 = collected[0]
    assert bundle_jan2.bars["AAPL"].is_delisted is False

    handler.update_bars()  # Jan 3 — AAPL exit bar
    bundle_jan3 = collected[1]
    assert bundle_jan3.bars["AAPL"].is_delisted is True


def test_handler_excludes_symbol_after_exit_bar():
    """After the exit bar, the symbol no longer appears in bundles."""
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    ub = _make_universe_builder({"AAPL": datetime(2020, 1, 3)})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch, universe_builder=ub)
    while handler.update_bars():
        pass
    # Jan 4 bundle (after AAPL exit) must not contain AAPL
    last_bundle = collected[-1]
    assert "AAPL" not in last_bundle.bars


def test_handler_without_universe_builder_unchanged():
    """Passing no universe_builder preserves existing behaviour — no is_delisted bars."""
    fetch = _make_fetch({"AAPL": AAPL_ROWS, "MSFT": MSFT_ROWS})
    collected = []
    handler = YahooDataHandler(collected.append, ["AAPL", "MSFT"], "2020-01-01", "2020-01-05", fetch=fetch)
    while handler.update_bars():
        pass
    assert all(not bar.is_delisted for bundle in collected for bar in bundle.bars.values())
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_yahoo_data_handler.py::test_handler_marks_exit_bar_as_delisted tests/test_yahoo_data_handler.py::test_handler_excludes_symbol_after_exit_bar tests/test_yahoo_data_handler.py::test_handler_without_universe_builder_unchanged -v
```

Expected: FAIL — `TypeError: YahooDataHandler.__init__() got unexpected keyword argument 'universe_builder'`

- [ ] **Step 3: Add universe_builder to `YahooDataHandler`**

In `trading/impl/yahoo_data_handler.py`, update the constructor signature:

```python
from ..base.universe_builder import UniverseBuilder

def __init__(
    self,
    emit:             Callable[[Event], None],
    symbols:          list[str],
    start:            str,
    end:              str,
    fetch:            Callable[[list[str], str, str], dict[str, list[dict]]],
    max_history:      int = 200,
    universe_builder: "UniverseBuilder | None" = None,
):
```

Replace the `_merged` construction loop (the `for ts in timeline:` block) with this version that applies point-in-time gating:

```python
_was_active: dict[str, bool] = {s: True for s in symbols}
self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
for ts in timeline:
    bundle: dict[str, TickEvent] = {}
    for symbol in symbols:
        if ts in raw[symbol]:
            bar = raw[symbol][ts]
            last_real[symbol] = bar
        elif last_real[symbol] is not None:
            prev = last_real[symbol]
            bar = TickEvent(
                symbol=symbol, timestamp=ts,
                open=prev.close, high=prev.close, low=prev.close, close=prev.close,
                volume=0.0, is_synthetic=True,
            )
        else:
            bar = TickEvent(
                symbol=symbol, timestamp=ts,
                open=0.0, high=0.0, low=0.0, close=0.0,
                volume=0.0, is_synthetic=True,
            )

        if universe_builder is not None:
            is_now_active = universe_builder.is_active(symbol, ts)
            if not is_now_active and _was_active[symbol]:
                # Transition bar: emit once with is_delisted=True so portfolio can exit
                bar = TickEvent(
                    symbol=bar.symbol, timestamp=bar.timestamp,
                    open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                    volume=bar.volume, is_synthetic=bar.is_synthetic, is_delisted=True,
                )
            elif not is_now_active:
                # Already exited — exclude from bundle
                _was_active[symbol] = False
                continue
            _was_active[symbol] = is_now_active

        bundle[symbol] = bar
    self._merged.append((ts, bundle))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_yahoo_data_handler.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/yahoo_data_handler.py tests/test_yahoo_data_handler.py
git commit -m "feat: inject universe_builder into YahooDataHandler for is_delisted gating"
```

---

## Task 6: `MultiCSVDataHandler` — universe_builder injection

**Files:**
- Modify: `trading/impl/multi_csv_data_handler.py`
- Modify: `tests/test_data.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_data.py`:

```python
from unittest.mock import MagicMock
from trading.base.universe_builder import UniverseBuilder


def _make_universe_builder_csv(active_until: dict[str, datetime]):
    builder = MagicMock(spec=UniverseBuilder)
    def is_active(symbol, timestamp):
        if symbol not in active_until:
            return True
        return timestamp < active_until[symbol]
    builder.is_active.side_effect = is_active
    return builder


def test_csv_handler_marks_exit_bar_as_delisted():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        # AAPL exits on 2020-01-03 (that bar is the delisted transition bar)
        ub = _make_universe_builder_csv({"AAPL": datetime(2020, 1, 3)})
        collected = []
        handler = MultiCSVDataHandler(collected.append, ["AAPL", "MSFT"], [aapl, msft], universe_builder=ub)
        handler.update_bars()  # 2020-01-02 — AAPL active
        assert collected[0].bars["AAPL"].is_delisted is False
        handler.update_bars()  # 2020-01-03 — AAPL exit bar
        assert collected[1].bars["AAPL"].is_delisted is True
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_csv_handler_excludes_symbol_after_exit_bar():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        ub = _make_universe_builder_csv({"AAPL": datetime(2020, 1, 3)})
        collected = []
        handler = MultiCSVDataHandler(collected.append, ["AAPL", "MSFT"], [aapl, msft], universe_builder=ub)
        while handler.update_bars():
            pass
        # 2020-01-04 bundle must not contain AAPL
        last_bundle = collected[-1]
        assert "AAPL" not in last_bundle.bars
    finally:
        os.unlink(aapl)
        os.unlink(msft)


def test_csv_handler_without_universe_builder_unchanged():
    aapl = make_csv(AAPL_ROWS)
    msft = make_csv(MSFT_ROWS)
    try:
        collected = []
        handler = MultiCSVDataHandler(collected.append, ["AAPL", "MSFT"], [aapl, msft])
        while handler.update_bars():
            pass
        assert all(not bar.is_delisted for bundle in collected for bar in bundle.bars.values())
    finally:
        os.unlink(aapl)
        os.unlink(msft)
```

Also add `from datetime import datetime` to the imports at the top of `tests/test_data.py` if not already present.

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_data.py::test_csv_handler_marks_exit_bar_as_delisted tests/test_data.py::test_csv_handler_excludes_symbol_after_exit_bar tests/test_data.py::test_csv_handler_without_universe_builder_unchanged -v
```

Expected: FAIL — `TypeError: MultiCSVDataHandler.__init__() got unexpected keyword argument 'universe_builder'`

- [ ] **Step 3: Add universe_builder to `MultiCSVDataHandler`**

In `trading/impl/multi_csv_data_handler.py`, update the constructor signature:

```python
from ..base.universe_builder import UniverseBuilder

def __init__(
    self,
    emit:             Callable[[Event], None],
    symbols:          list[str],
    csv_paths:        list[str] | None = None,
    start:            str | None = None,
    end:              str | None = None,
    max_history:      int = 200,
    date_format:      str = "%Y-%m-%d",
    universe_builder: "UniverseBuilder | None" = None,
):
```

Replace the `_merged` construction block (the `for ts in timeline:` block) with the identical gating logic used in Task 5:

```python
_was_active: dict[str, bool] = {s: True for s in symbols}
self._merged: list[tuple[datetime, dict[str, TickEvent]]] = []
for ts in timeline:
    bundle: dict[str, TickEvent] = {}
    for symbol in symbols:
        if ts in raw[symbol]:
            bar = raw[symbol][ts]
            last_real[symbol] = bar
        elif last_real[symbol] is not None:
            prev = last_real[symbol]
            bar = TickEvent(
                symbol=symbol, timestamp=ts,
                open=prev.close, high=prev.close, low=prev.close, close=prev.close,
                volume=0.0, is_synthetic=True,
            )
        else:
            bar = TickEvent(
                symbol=symbol, timestamp=ts,
                open=0.0, high=0.0, low=0.0, close=0.0,
                volume=0.0, is_synthetic=True,
            )

        if universe_builder is not None:
            is_now_active = universe_builder.is_active(symbol, ts)
            if not is_now_active and _was_active[symbol]:
                bar = TickEvent(
                    symbol=bar.symbol, timestamp=bar.timestamp,
                    open=bar.open, high=bar.high, low=bar.low, close=bar.close,
                    volume=bar.volume, is_synthetic=bar.is_synthetic, is_delisted=True,
                )
            elif not is_now_active:
                _was_active[symbol] = False
                continue
            _was_active[symbol] = is_now_active

        bundle[symbol] = bar
    self._merged.append((ts, bundle))
```

- [ ] **Step 4: Run tests to verify they pass**

```
pytest tests/test_data.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/multi_csv_data_handler.py tests/test_data.py
git commit -m "feat: inject universe_builder into MultiCSVDataHandler for is_delisted gating"
```

---

## Task 7: `SimplePortfolio` — force-exit on `is_delisted`

**Files:**
- Modify: `trading/impl/simple_portfolio.py`
- Modify: `tests/test_portfolio.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_portfolio.py`:

```python
def _delisted_bar(symbol: str, open_price: float, ts=None):
    ts = ts or datetime(2020, 1, 3)
    tick = TickEvent(
        symbol=symbol, timestamp=ts,
        open=open_price, high=open_price, low=open_price, close=open_price,
        volume=1000.0, is_delisted=True,
    )
    return BarBundleEvent(timestamp=ts, bars={symbol: tick})


def test_delisted_bar_force_closes_open_position():
    """Portfolio force-sells an open position when is_delisted=True, even with no signal."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    # Open a long position first
    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    collected.clear()

    # Simulate fill from the buy
    portfolio.on_fill(_fill("AAPL", "BUY", 100, 100.0))

    # Next bar: AAPL is delisted, no pending signal
    portfolio.fill_pending_orders(_delisted_bar("AAPL", 95.0))

    orders = [o for o in collected if isinstance(o, OrderEvent) and o.direction == "SELL"]
    assert len(orders) == 1
    assert orders[0].symbol == "AAPL"
    assert orders[0].quantity == 100


def test_delisted_bar_with_no_position_emits_no_sell():
    """No position open — a delisted bar must not emit a spurious SELL."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.fill_pending_orders(_delisted_bar("AAPL", 95.0))

    sell_orders = [o for o in collected if isinstance(o, OrderEvent) and o.direction == "SELL"]
    assert len(sell_orders) == 0


def test_signal_for_delisted_symbol_is_ignored():
    """Even if a strategy sends a BUY signal for a delisted symbol, no order is placed."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_delisted_bar("AAPL", 100.0))

    buy_orders = [o for o in collected if isinstance(o, OrderEvent) and o.direction == "BUY"]
    assert len(buy_orders) == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_portfolio.py::test_delisted_bar_force_closes_open_position tests/test_portfolio.py::test_delisted_bar_with_no_position_emits_no_sell tests/test_portfolio.py::test_signal_for_delisted_symbol_is_ignored -v
```

Expected: FAIL — force-close not yet implemented, signal-skip not yet implemented.

- [ ] **Step 3: Add force-exit pre-pass to `fill_pending_orders`**

In `trading/impl/simple_portfolio.py`, replace the beginning of `fill_pending_orders` up to the signals loop:

```python
def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None:
    pending = self._pending_signals
    self._pending_signals = None
    emitted_any = False

    # Pre-pass: force-close any position in a symbol that exited the universe this bar.
    for symbol, bar in bar_bundle.bars.items():
        if bar.is_delisted and self._holdings.get(symbol, 0) != 0:
            self._emit_order(symbol, bar_bundle.timestamp, "SELL", abs(self._holdings[symbol]), bar)
            emitted_any = True

    if not pending:
        self._current_attribution = {}
        if not emitted_any:
            self._emit_order("", bar_bundle.timestamp, "HOLD", 0)
        return

    self._current_attribution = pending.per_strategy

    # Compute current holdings market value for leverage check
    holdings_value = sum(
        self._holdings.get(s, 0) * bars[-1].close
        for s in self._symbols
        if (bars := self._get_bars(s, 1))
    )
    current_equity = self._cash + holdings_value
    max_gross_exposure = current_equity * self._max_leverage

    available_cash = self._cash
    for symbol, signal_event in pending.combined.items():
        bar = bar_bundle.bars.get(symbol)
        # Skip symbols absent from bundle or on their exit bar
        if bar is None or bar.is_delisted:
            continue
        # No shorts: clamp negative signals to zero
        weight = max(0.0, signal_event.signal)
        price = bar.open
        if price <= 0:
            continue

        target_qty = int(weight * self._initial_capital / price)
        delta      = target_qty - self._holdings.get(symbol, 0)

        if delta > 0:
            max_qty_by_cash = int(available_cash / (price * (1.0 + self._fill_cost_buffer)))
            current_exposure = holdings_value + (self._cash - available_cash)
            max_qty_by_leverage = max(0, int((max_gross_exposure - current_exposure) / price))
            affordable_qty = min(delta, max_qty_by_cash, max_qty_by_leverage)
            if affordable_qty > 0:
                available_cash -= affordable_qty * price * (1.0 + self._fill_cost_buffer)
                self._emit_order(symbol, bar_bundle.timestamp, "BUY", affordable_qty, bar)
                emitted_any = True
        elif delta < 0:
            self._emit_order(symbol, bar_bundle.timestamp, "SELL", abs(delta), bar)
            emitted_any = True

    if not emitted_any:
        self._emit_order("", bar_bundle.timestamp, "HOLD", 0)
```

- [ ] **Step 4: Run all portfolio tests**

```
pytest tests/test_portfolio.py -v
```

Expected: all PASS

- [ ] **Step 5: Commit**

```bash
git add trading/impl/simple_portfolio.py tests/test_portfolio.py
git commit -m "feat: force-exit positions on is_delisted bars in SimplePortfolio"
```

---

## Task 8: `run_backtest.py` wiring

**Files:**
- Modify: `run_backtest.py`

- [ ] **Step 1: Add config constants and optional wiring**

Replace the configuration block and `data =` line in `run_backtest.py`:

```python
# --- Configuration -----------------------------------------------------------
START               = "2020-01-01"
END                 = "2022-01-01"
STRATEGY_PARAMS_DIR = "strategy_params"
INITIAL_CAPITAL     = 10_000.0
COMMISSION_PCT      = 0.001   # 0.1% of trade value per fill
SLIPPAGE_PCT        = 0.0005  # fixed spread floor (one-way minimum cost)
MARKET_IMPACT_ETA   = 0.1     # square-root impact coefficient (Almgren et al.)
MAX_LEVERAGE        = 1.0     # max gross exposure as a multiple of current equity
FILL_COST_BUFFER    = 0.002   # cash reserve fraction for slippage + commission on buys
RESULTS_DIR         = "results"
RESULTS_FORMAT      = "parquet"  # "parquet" or "csv"
# Universe gating (survivorship-bias correction) --------------------------------
USE_UNIVERSE_GATING = False    # True = enable point-in-time universe gating
INDEX_CODE          = "sp500"  # index code for yfiua/index-constituents (e.g. sp500, nasdaq100)
RELOAD_UNIVERSE     = False    # True = re-fetch manifest even if data/universe_manifest.csv exists
# -----------------------------------------------------------------------------
```

Replace the `data = YahooDataHandler(...)` block:

```python
universe_builder = None
if USE_UNIVERSE_GATING:
    from external.index_constituents import load_or_fetch_universe_manifest
    from trading.impl import IndexConstituentsUniverseBuilder
    manifest_path    = load_or_fetch_universe_manifest(
        INDEX_CODE, START, END,
        output_path="data/universe_manifest.csv",
        reload=RELOAD_UNIVERSE,
    )
    universe_builder = IndexConstituentsUniverseBuilder(manifest_path)

data = YahooDataHandler(
    events.put, symbols, start=START, end=END,
    fetch=fetch_daily_bars,
    universe_builder=universe_builder,   # None = current behaviour, no gating
)
```

- [ ] **Step 2: Run the full test suite**

```
pytest -v
```

Expected: all PASS — no regressions in existing tests, new tests green.

- [ ] **Step 3: Smoke-test the backtest with gating off (existing behaviour)**

```
python run_backtest.py
```

Expected: runs to completion, writes results, no errors. (`USE_UNIVERSE_GATING = False` so no HTTP calls made.)

- [ ] **Step 4: Commit**

```bash
git add run_backtest.py
git commit -m "feat: wire IndexConstituentsUniverseBuilder into run_backtest.py with USE_UNIVERSE_GATING toggle"
```

---

## Self-Review

**Spec coverage check:**

| Spec requirement | Task covering it |
|---|---|
| `is_delisted: bool = False` on `TickEvent` | Task 1 |
| `UniverseBuilder` ABC (`is_active`, `exit_date`, `all_symbols`) | Task 2 |
| `IndexConstituentsUniverseBuilder` reads manifest CSV | Task 3 |
| `external/index_constituents.py` — monthly snapshot fetch + disk cache | Task 4 |
| `YahooDataHandler` injection + exit bar marking + exclusion | Task 5 |
| `MultiCSVDataHandler` injection (same pattern) | Task 6 |
| `SimplePortfolio` force-exit pre-pass + signal skip for delisted | Task 7 |
| `run_backtest.py` `USE_UNIVERSE_GATING` / `INDEX_CODE` / `RELOAD_UNIVERSE` | Task 8 |
| `trading/base/__init__.py` exports `UniverseBuilder` | Task 2 |
| `trading/impl/__init__.py` exports `IndexConstituentsUniverseBuilder` | Task 3 |

**No placeholder scan:** All steps contain complete code. No TBDs.

**Type consistency check:** `UniverseBuilder` defined in Task 2 and used in Tasks 3, 5, 6 — names match. `IndexConstituentsUniverseBuilder` defined in Task 3 and imported in Task 8 — names match. `is_delisted` field added in Task 1, checked in Tasks 5, 6, 7 — consistent. `_was_active` dict pattern identical in Tasks 5 and 6. `fetch_universe_manifest` signature in Task 4 (`index_code, start, end, output_path`) matches call site in Task 8.
