# Universe Manifest Per-Index Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Store universe manifests at `data/universe_manifest/{index_code}.csv` instead of a single flat `data/universe_manifest.csv`, so manifests for different indices don't overwrite each other.

**Architecture:** Remove the `output_path` parameter from both public functions; derive the path deterministically from `index_code`. Callers (run_backtest.py) drop the `UNIVERSE_MANIFEST_FILE` constant and the `output_path=` kwarg. Existing tests already pass an explicit `output_path` via tempdir, so they continue to work unchanged; one new test covers the default-path derivation.

**Tech Stack:** Python stdlib only (csv, os, urllib).

---

### Task 1: Update `external/index_constituents.py` — derive default path from `index_code`

**Files:**
- Modify: `external/index_constituents.py:30-99`

- [ ] **Step 1: Write the failing test for default path derivation**

Add to `tests/test_index_constituents_external.py`:

```python
def test_default_output_path_derived_from_index_code():
    """Default path is data/universe_manifest/{index_code}.csv"""
    import external.index_constituents as mod
    import inspect
    sig = inspect.signature(mod.fetch_universe_manifest)
    # output_path parameter must be gone (or have no default)
    assert "output_path" not in sig.parameters, (
        "output_path should be removed; path is derived from index_code"
    )


def test_fetch_writes_to_index_derived_path():
    with tempfile.TemporaryDirectory() as tmpdir:
        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)):
            with patch("os.makedirs"):
                # patch open to capture the path used
                import builtins
                opened_paths = []
                real_open = builtins.open
                def tracking_open(path, *args, **kwargs):
                    opened_paths.append(path)
                    return real_open(os.path.join(tmpdir, "out.csv"), *args, **kwargs)
                with patch("builtins.open", side_effect=tracking_open):
                    fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")
                assert any("sp500" in p for p in opened_paths)
```

- [ ] **Step 2: Run the test to confirm it fails**

```
pytest tests/test_index_constituents_external.py::test_default_output_path_derived_from_index_code -v
```
Expected: FAIL — `output_path` still present in signature.

- [ ] **Step 3: Implement — remove `output_path`, derive path from `index_code`**

Replace `external/index_constituents.py` with:

```python
import csv
import io
import os
import urllib.request
from datetime import datetime


_BASE_URL = "https://yfiua.github.io/index-constituents"
_MANIFEST_DIR = "data/universe_manifest"


def _iter_months(start_dt: datetime, end_dt: datetime):
    year = start_dt.year
    month = start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_month_date(year: int, month: int) -> str:
    month += 1
    if month > 12:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}-01"


def _manifest_path(index_code: str) -> str:
    return os.path.join(_MANIFEST_DIR, f"{index_code}.csv")


def fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
) -> str:
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    history: dict[str, dict[str, tuple[int, int]]] = {}
    fetched_months: list[tuple[int, int]] = []

    for year, month in _iter_months(start_dt, end_dt):
        url = f"{_BASE_URL}/{year:04d}/{month:02d}/constituents-{index_code}.csv"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode()
        except Exception:
            continue

        fetched_months.append((year, month))

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

    last_fetched_ym = max(fetched_months)

    rows = []
    for symbol, info in sorted(history.items()):
        enter_year, enter_month = info["enter"]
        last_year, last_month = info["last_seen"]
        exit_date = ""
        if (last_year, last_month) < last_fetched_ym:
            exit_date = _next_month_date(last_year, last_month)
        rows.append(
            {
                "symbol": symbol,
                "enter_date": f"{enter_year:04d}-{enter_month:02d}-01",
                "exit_date": exit_date,
            }
        )

    output_path = _manifest_path(index_code)
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def load_or_fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
    reload: bool = False,
) -> str:
    output_path = _manifest_path(index_code)
    if not reload and os.path.exists(output_path):
        return output_path
    return fetch_universe_manifest(index_code, start, end)
```

- [ ] **Step 4: Run the signature test to confirm it passes**

```
pytest tests/test_index_constituents_external.py::test_default_output_path_derived_from_index_code -v
```
Expected: PASS.

---

### Task 2: Update tests to drop `output_path=` kwarg from all existing calls

**Files:**
- Modify: `tests/test_index_constituents_external.py`

The existing tests pass `output_path=out` (a tmpdir path) to isolate writes. Since `output_path` is now removed, these tests need to patch `external.index_constituents._manifest_path` instead.

- [ ] **Step 1: Confirm existing tests fail after Task 1**

```
pytest tests/test_index_constituents_external.py -v
```
Expected: multiple FAILs — `TypeError: unexpected keyword argument 'output_path'`.

- [ ] **Step 2: Rewrite the test file**

Replace `tests/test_index_constituents_external.py` with:

```python
import csv
import os
import tempfile
from unittest.mock import MagicMock, patch

import pytest

from external.index_constituents import fetch_universe_manifest, load_or_fetch_universe_manifest


def _mock_urlopen(responses: dict[str, str]):
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


JAN_CSV = "Symbol,Name\nAAPL,Apple\nENRN,Enron\n"
FEB_CSV = "Symbol,Name\nAAPL,Apple\n"


def test_fetch_saves_manifest_csv():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)), \
             patch("external.index_constituents._manifest_path", return_value=out):
            result_path = fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")

        assert result_path == out
        assert os.path.exists(out)
        with open(out, newline="") as f:
            rows = {row["symbol"]: row for row in csv.DictReader(f)}
        assert rows["AAPL"]["enter_date"] == "2020-01-01"
        assert rows["AAPL"]["exit_date"] == ""
        assert rows["ENRN"]["enter_date"] == "2020-01-01"
        assert rows["ENRN"]["exit_date"] == "2020-02-01"


def test_fetch_skips_missing_months_gracefully():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        responses = {"2020/01": JAN_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)), \
             patch("external.index_constituents._manifest_path", return_value=out):
            fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")
        with open(out, newline="") as f:
            rows = list(csv.DictReader(f))
        assert len(rows) == 2


def test_fetch_raises_on_no_data():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen({})), \
             patch("external.index_constituents._manifest_path", return_value=out):
            with pytest.raises(ValueError, match="No constituent data"):
                fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01")


def test_load_or_fetch_skips_http_when_file_exists():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            writer.writeheader()
            writer.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        with patch("external.index_constituents.urllib.request.urlopen") as mock_open, \
             patch("external.index_constituents._manifest_path", return_value=out):
            result = load_or_fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", reload=False)
            mock_open.assert_not_called()

        assert result == out


def test_load_or_fetch_refetches_when_reload_true():
    with tempfile.TemporaryDirectory() as tmpdir:
        out = os.path.join(tmpdir, "sp500.csv")
        with open(out, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
            writer.writeheader()
            writer.writerow({"symbol": "AAPL", "enter_date": "2020-01-01", "exit_date": ""})

        responses = {"2020/01": JAN_CSV, "2020/02": FEB_CSV}
        with patch("external.index_constituents.urllib.request.urlopen", side_effect=_mock_urlopen(responses)), \
             patch("external.index_constituents._manifest_path", return_value=out):
            load_or_fetch_universe_manifest("sp500", "2020-01-01", "2020-03-01", reload=True)

        with open(out, newline="") as f:
            symbols = {row["symbol"] for row in csv.DictReader(f)}
        assert symbols == {"AAPL", "ENRN"}


def test_manifest_path_uses_index_code():
    from external.index_constituents import _manifest_path
    path = _manifest_path("sp500")
    assert path == os.path.join("data", "universe_manifest", "sp500.csv")

    path2 = _manifest_path("nasdaq100")
    assert path2 == os.path.join("data", "universe_manifest", "nasdaq100.csv")
```

- [ ] **Step 3: Run all tests to confirm they pass**

```
pytest tests/test_index_constituents_external.py -v
```
Expected: 6 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add external/index_constituents.py tests/test_index_constituents_external.py
git commit -m "refactor: derive universe manifest path from index_code (data/universe_manifest/{index}.csv)"
```

---

### Task 3: Update `run_backtest.py` — remove `UNIVERSE_MANIFEST_FILE` and `output_path=` kwarg

**Files:**
- Modify: `run_backtest.py:36,52-58`

- [ ] **Step 1: Remove `UNIVERSE_MANIFEST_FILE` constant and drop `output_path=` from the call**

In `run_backtest.py`, replace:

```python
UNIVERSE_MANIFEST_FILE = "data/universe_manifest.csv"
```
with nothing (delete the line), and replace:

```python
    manifest_path = load_or_fetch_universe_manifest(
        INDEX_CODE,
        START,
        END,
        output_path=UNIVERSE_MANIFEST_FILE,
        reload=RELOAD_UNIVERSE,
    )
```
with:

```python
    manifest_path = load_or_fetch_universe_manifest(
        INDEX_CODE,
        START,
        END,
        reload=RELOAD_UNIVERSE,
    )
```

- [ ] **Step 2: Run the full test suite to confirm nothing broke**

```
pytest tests/ -v --ignore=tests/test_index_constituents_external.py -x
```
Expected: all existing tests PASS (or same pass/fail ratio as before this plan).

- [ ] **Step 3: Commit**

```bash
git add run_backtest.py
git commit -m "chore: remove UNIVERSE_MANIFEST_FILE constant; path derived from INDEX_CODE"
```

---

## Self-Review

**Spec coverage:**
- "store all universe into one single file" — each index gets exactly one file ✓
- "store universe manifest by index" — path includes `index_code` ✓
- "correct structure: data/universe_manifest/sp500" — `_manifest_path("sp500")` returns `data/universe_manifest/sp500.csv` ✓

**Placeholder scan:** None found. All code blocks are complete.

**Type consistency:** `_manifest_path` defined in Task 1, patched as `external.index_constituents._manifest_path` in Task 2 tests — consistent. `load_or_fetch_universe_manifest` signature (without `output_path`) used identically in Tasks 1, 2, and 3.
