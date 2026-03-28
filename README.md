# Event-Driven Trading & Backtesting POC

A minimal, extensible event-driven trading engine and backtester written in pure Python (stdlib only).

## Architecture

All components communicate through an `emit: Callable[[Event], None]` injected at construction — no direct cross-component calls. The concrete `queue.Queue` is owned by `run_backtest.py` and `Backtester` only.

```
DataHandler → BarBundleEvent → Strategy → SignalBundleEvent → Portfolio → OrderEvent → ExecutionHandler → FillEvent → Portfolio
```

| Component | File | Responsibility |
|---|---|---|
| `DataHandler` | `trading/impl/data.py` | Replays historical bars; emits `BarBundleEvent` |
| `Strategy` | `trading/impl/strategy.py` | Consumes bar bundles; emits `SignalBundleEvent` |
| `Portfolio` | `trading/impl/portfolio.py` | Sizes positions; emits `OrderEvent`; tracks equity |
| `ExecutionHandler` | `trading/impl/execution.py` | Simulates fills; emits `FillEvent` |
| `Backtester` | `trading/backtester.py` | Owns the event queue; drives the main loop |

### Event types

```
BarBundleEvent    timestamp, bars: dict[symbol → TickEvent]
SignalBundleEvent timestamp, signals: dict[symbol → SignalEvent]
SignalEvent       symbol, timestamp, signal_type (LONG | EXIT), strength  [value type, not queued]
OrderEvent        timestamp, symbol, order_type, direction (BUY | SELL), quantity, reference_price
FillEvent         timestamp, symbol, direction, quantity, fill_price, commission
```

## Quickstart

```bash
# 1. Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate

# 2. Install dependencies
pip install -r requirements.txt

# 3. Register the Jupyter kernel
python -m ipykernel install --user --name=vibe-quant

# 4. Generate synthetic OHLCV data (540 trading days)
python generate_data.py

# 5. Run the backtest
python run_backtest.py

# 6. Visualize results (select the "vibe-quant" kernel in the notebook)
jupyter notebook plot_results.ipynb
```

Output:

```
Initial capital : $ 10,000.00
Final equity    : $  7,834.38
Total return    : -21.66%
Trades (fills)  : 28
Equity curve    : results/equity_curve.csv
```

## Configuration

Edit the constants at the top of `run_backtest.py`:

```python
SYMBOLS         = ["AAPL"]                   # add more symbols to trade multiple
CSV_PATHS       = ["data/sample_data.csv"]   # one CSV per symbol, same order
INITIAL_CAPITAL = 10_000.0
FAST_WINDOW     = 10      # SMA crossover fast period
SLOW_WINDOW     = 30      # SMA crossover slow period
COMMISSION      = 1.0     # dollars per fill
SLIPPAGE_PCT    = 0.0005  # 0.05% per fill
```

## CSV format

`data/sample_data.csv` must have these columns (header required):

```
timestamp,open,high,low,close,volume
2020-01-02,150.0,151.2,149.3,150.8,1200000
...
```

Default date format is `%Y-%m-%d`. Override via `date_format` on `MultiCSVDataHandler`. Missing bars for a given timestamp are zero-filled automatically.

## Implementing a custom strategy

Create a new file in `trading/impl/` and subclass `Strategy`:

```python
# trading/impl/my_strategy.py
from typing import Callable
from ..base.strategy import Strategy
from ..events import BarBundleEvent, Event, SignalBundleEvent, SignalEvent, TickEvent

class MyStrategy(Strategy):
    def __init__(
        self,
        emit:     Callable[[Event], None],
        symbols:  list[str],
        get_bars: Callable[[str, int], list[TickEvent]],
    ):
        super().__init__(emit, get_bars)
        self._symbols = symbols

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        signals = {}
        for symbol in self._symbols:
            bars = self.get_bars(symbol, 50)
            # ... compute indicator ...
            signals[symbol] = SignalEvent(
                symbol=symbol,
                timestamp=event.timestamp,
                signal_type="LONG",
            )
        return SignalBundleEvent(timestamp=event.timestamp, signals=signals) if signals else None
```

Then swap it into `run_backtest.py`:

```python
from trading.impl.my_strategy import MyStrategy
strategy = MyStrategy(events.put, SYMBOLS, data.get_latest_bars)
```

## Project structure

```
.
├── trading/
│   ├── base/
│   │   ├── data.py          # DataHandler ABC
│   │   ├── strategy.py      # Strategy ABC
│   │   ├── portfolio.py     # Portfolio ABC
│   │   └── execution.py     # ExecutionHandler ABC
│   ├── impl/
│   │   ├── data.py          # MultiCSVDataHandler
│   │   ├── strategy.py      # SMACrossoverStrategy
│   │   ├── portfolio.py     # SimplePortfolio
│   │   └── execution.py     # SimulatedExecutionHandler
│   ├── events.py            # all event dataclasses + EventType enum
│   └── backtester.py        # event loop
├── data/
│   └── sample_data.csv
├── results/
│   └── equity_curve.csv
├── generate_data.py         # synthetic data generator
├── run_backtest.py          # entry point
├── plot_results.ipynb       # equity curve, drawdown, trade markers, summary stats
└── requirements.txt
```

## Requirements

Python 3.10+ (uses `match` statement).

| Package | Purpose |
|---|---|
| `matplotlib>=3.7` | `plot_results.ipynb` — equity curve, drawdown, trade markers |
| `ipykernel` | Registers the venv as a Jupyter kernel (`claude-learn`) |
| `pytest>=7.0` | Test suite (`tests/`) |
| `pandas>=2.0` | Optional — cleaner post-run analysis (not used yet) |

Install: `pip install -r requirements.txt`

## Extension points

- **RiskManager** — insert between Portfolio and Execution to enforce max drawdown / position limits
- **Live trading** — replace `MultiCSVDataHandler` with a streaming data source; replace `SimulatedExecutionHandler` with a broker API client
- **PerformanceAnalyzer** — consume the equity curve to compute Sharpe ratio, max drawdown, CAGR

