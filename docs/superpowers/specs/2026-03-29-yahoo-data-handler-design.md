# Yahoo Finance Data Handler — Design

**Date:** 2026-03-29
**Status:** Approved

## Overview

Add a `YahooDataHandler` that fetches historical daily bars from Yahoo Finance and replays them through the existing event-driven backtester. A thin helper module in `external/yahoo.py` wraps the `yfinance` dependency; the engine itself stays dependency-free.

## Architecture

```
external/
  yahoo.py                    ← fetch_daily_bars() — only file that imports yfinance

trading/impl/
  yahoo_data_handler.py       ← YahooDataHandler — engine impl, no external imports
```

`external/` sits outside `trading/` to make the dependency boundary explicit. Nothing inside `trading/` imports from `external/`.

## Components

### `external/yahoo.py`

Single public function:

```python
def fetch_daily_bars(symbol: str, start: str, end: str) -> list[dict]:
    ...
```

- Calls `yfinance.download(symbol, start=start, end=end, auto_adjust=True)`
- Iterates the resulting DataFrame and returns `list[dict]` with keys:
  `timestamp` (datetime), `open`, `high`, `low`, `close`, `volume` (floats)
- Raises `ValueError` if the ticker is unknown or the date range returns no data

### `trading/impl/yahoo_data_handler.py`

```python
class YahooDataHandler(DataHandler):
    def __init__(
        self,
        emit:        Callable[[Event], None],
        symbols:     list[str],
        start:       str,          # "YYYY-MM-DD"
        end:         str,          # "YYYY-MM-DD"
        max_history: int = 200,
    ): ...

    def update_bars(self) -> bool: ...
    def get_latest_bars(self, symbol: str, n: int = 1) -> list[TickEvent]: ...
```

- Calls `fetch_daily_bars` once per symbol at construction (sequential)
- Raises `ValueError` immediately if any symbol returns no data
- Merges all symbol timelines into a unified sorted list, zero-filling missing bars (same logic as `MultiCSVDataHandler`)
- Replay via `_merged` list + `_history` deques — identical to `MultiCSVDataHandler`

## Data Flow

```
YahooDataHandler.__init__
  └─ fetch_daily_bars(symbol, start, end)   [per symbol, at startup]
       └─ yfinance.download()
  └─ merge timelines → self._merged

bt.run() loop
  └─ update_bars()
       └─ emit(BarBundleEvent)
```

## Error Handling

| Scenario | Behaviour |
|---|---|
| Unknown ticker | `ValueError` raised in `fetch_daily_bars` |
| Empty date range | `ValueError` raised in `fetch_daily_bars` |
| Symbol missing on some dates | Zero-filled `TickEvent` (same as CSV handler) |

## Testing

### Unit tests — `tests/test_yahoo_data_handler.py`
Monkey-patch `external.yahoo.fetch_daily_bars`. No network, no yfinance import. Covers:
- Correct timeline union across symbols
- `update_bars` emits `BarBundleEvent`
- `get_latest_bars` returns correct history slice
- Exhaustion returns `False`
- Unknown symbol raises `ValueError`

### Integration tests — `tests/test_yahoo_external.py`
Marked `@pytest.mark.integration` — skipped by default. Run with `pytest -m integration`. Covers a real network fetch for a known ticker over a short date range.

## Usage in `run_backtest.py`

```python
from trading.impl import YahooDataHandler

data = YahooDataHandler(events.put, symbols, start="2020-01-01", end="2022-01-01")
```

`CSV_MAP` and `CSV_PATHS` are no longer needed when using this handler.

## Dependencies

- Add `yfinance` to `requirements.txt`
- `external/yahoo.py` is the only file that imports it
