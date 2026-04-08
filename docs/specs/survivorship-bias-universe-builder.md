# Survivorship-Bias-Free Universe Construction

## Problem

`YahooDataHandler` only returns data for currently-listed symbols. Any universe that
implicitly or explicitly filters on "currently exists" introduces **survivorship bias**:
strategies appear more profitable because they never held stocks that went to zero or
were delisted.

Two distinct gaps:

1. **Missing delisted data** — Yahoo Finance silently omits symbols no longer listed
   today. No error, no warning; the universe is just cleaner than reality.
2. **No point-in-time gating** — the `symbols` list is fixed at construction. There is
   no mechanism to say "ENRN was in the universe from 1995-01-01 to 2001-12-02" and
   automatically exit the position when it left.

---

## Solution Overview

Three components added; two existing components updated:

```
Tiingo API
    │ (first run or RELOAD_FROM_TIINGO=True)
    ▼
data/universe_manifest.csv
    │
    ▼
TiingoUniverseBuilder.is_active(symbol, ts)
    │ injected into
    ▼
YahooDataHandler / MultiCSVDataHandler  ← marks TickEvent.is_delisted=True on exit bar
    │                                      excludes already-exited symbols from bundle
    ▼
BarBundleEvent → SimplePortfolio.fill_pending_orders
    │ pre-pass: force SELL any is_delisted bar with open position
    ▼
OrderEvent → SimulatedExecutionHandler
```

---

## Universe Manifest Format

`data/universe_manifest.csv`:

```
symbol,enter_date,exit_date
AAPL,2000-01-01,
MSFT,2000-01-01,
ENRN,1995-01-01,2001-12-02
LEHM,2003-01-01,2008-09-15
```

- Empty `exit_date` = symbol still active (no end gate)
- Source: Tiingo constituent history API (`/iex/` constituent endpoint)
- Cached to disk; re-fetched only when `RELOAD_FROM_TIINGO=True`

---

## Files to Create

### `external/tiingo.py`

Two public functions:

```python
def fetch_universe_manifest(
    index: str,         # e.g. "sp500"
    start: str,         # ISO date, inclusive
    end: str,           # ISO date, exclusive
    api_key: str,
    output_path: str = "data/universe_manifest.csv",
) -> str:
    """Calls Tiingo constituent history API, saves manifest CSV, returns path."""

def load_or_fetch_universe_manifest(
    index: str,
    start: str,
    end: str,
    api_key: str,
    output_path: str = "data/universe_manifest.csv",
    reload: bool = False,
) -> str:
    """
    Returns path to manifest CSV.
    If reload=False and file already exists, reads from disk.
    Otherwise calls fetch_universe_manifest.
    """
```

### `trading/base/universe_builder.py`

ABC — no business logic:

```python
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

### `trading/impl/tiingo_universe_builder.py`

Concrete implementation:

- Reads `data/universe_manifest.csv` in `__init__`
- Builds `dict[str, tuple[datetime, datetime | None]]` (symbol → enter, exit)
- `is_active`: returns `enter <= timestamp < exit` (open interval on exit side)
- `exit_date`: returns exit datetime or None
- `all_symbols`: returns all keys

---

## Files to Modify

### `trading/events.py`

Add `is_delisted: bool = False` to `TickEvent` after `is_synthetic`:

```python
@dataclass
class TickEvent:
    symbol:       str
    timestamp:    datetime
    open:         float
    high:         float
    low:          float
    close:        float
    volume:       float
    is_synthetic: bool = False
    is_delisted:  bool = False   # True on the last bar before universe exit
```

### `trading/impl/yahoo_data_handler.py` and `trading/impl/multi_csv_data_handler.py`

Add optional parameter to both constructors:

```python
universe_builder: UniverseBuilder | None = None,
```

In the `_merged` construction loop, after each bar is created, if `universe_builder`
is set, apply point-in-time gating:

```python
_was_active: dict[str, bool] = {s: True for s in symbols}

for ts in timeline:
    bundle: dict[str, TickEvent] = {}
    for symbol in symbols:
        bar = ...  # existing bar creation logic (real, carry-forward, or zero-fill)

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
                # Symbol already exited — exclude from bundle entirely
                _was_active[symbol] = False
                continue
            _was_active[symbol] = is_now_active

        bundle[symbol] = bar
    self._merged.append((ts, bundle))
```

### `trading/impl/simple_portfolio.py`

In `fill_pending_orders`, add a pre-pass **before** the signals loop:

```python
# Force-close positions in symbols that exited the universe this bar.
for symbol, bar in bar_bundle.bars.items():
    if bar.is_delisted and self._holdings.get(symbol, 0) != 0:
        self._emit_order(symbol, bar_bundle.timestamp, "SELL", abs(self._holdings[symbol]), bar)
        emitted_any = True
```

In the signals loop, skip delisted symbols so they are never re-entered:

```python
bar = bar_bundle.bars.get(symbol)
if bar is None or bar.is_delisted:
    continue
```

### `trading/base/__init__.py`

Add export: `from .universe_builder import UniverseBuilder`

### `trading/impl/__init__.py`

Add export: `from .tiingo_universe_builder import TiingoUniverseBuilder`

### `run_backtest.py`

Add configuration block and optional wiring:

```python
TIINGO_API_KEY     = ""          # set to enable point-in-time universe gating
TIINGO_INDEX       = "sp500"     # index to fetch constituents for
RELOAD_FROM_TIINGO = False       # True = re-fetch manifest even if file exists

universe_builder = None
if TIINGO_API_KEY:
    from external.tiingo import load_or_fetch_universe_manifest
    from trading.impl import TiingoUniverseBuilder
    manifest_path    = load_or_fetch_universe_manifest(
        TIINGO_INDEX, START, END, TIINGO_API_KEY, reload=RELOAD_FROM_TIINGO
    )
    universe_builder = TiingoUniverseBuilder(manifest_path)

data = YahooDataHandler(
    events.put, symbols, start=START, end=END,
    fetch=fetch_daily_bars,
    universe_builder=universe_builder,    # None = current behaviour unchanged
)
```

---

## What Does Not Change

- `DataHandler` ABC — no new abstract methods
- `StrategyContainer` — no changes
- `Strategy` implementations — no changes; strategies continue to call `get_bars` normally

---

## Data Source Guidance

Yahoo Finance does not carry delisted symbol price history. For a fully bias-free
backtest the price CSVs for delisted symbols must come from a provider that archives
them. Tiingo's API returns prices for most delisted US equities and is cost-effective
for research use. CSIData and Norgate Data are the professional alternatives.

The `MultiCSVDataHandler` + `TiingoUniverseBuilder` combination is the correct path
for universe-selection strategies: obtain per-symbol CSVs (including delisted) from
Tiingo, build the manifest via `external/tiingo.py`, and inject the builder.
