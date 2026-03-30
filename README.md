# Event-Driven Trading & Backtesting POC

A minimal, extensible event-driven trading engine and backtester written in pure Python (stdlib only).

## Architecture

All components communicate through an `emit: Callable[[Event], None]` injected at construction — no direct cross-component calls. The concrete `queue.Queue` is owned by `run_backtest.py` and `Backtester` only.

```
DataHandler → BarBundleEvent → StrategyContainer → SignalBundleEvent → Portfolio → OrderEvent → ExecutionHandler → FillEvent → Portfolio
```

| Component | File | Responsibility |
|---|---|---|
| `DataHandler` | `trading/impl/multi_csv_data_handler.py` / `yahoo_data_handler.py` | Replays historical bars; emits `BarBundleEvent` |
| `StrategyContainer` | `trading/impl/strategy_container.py` | Aggregates weighted signals from all strategies; emits one `SignalBundleEvent` per bar |
| `Strategy` | `strategies/sma_crossover_strategy.py` | Consumes bar bundles; returns `SignalBundleEvent` with normalised float weights |
| `Portfolio` | `trading/impl/simple_portfolio.py` | Rebalances to target weights; emits `OrderEvent`; tracks equity |
| `ExecutionHandler` | `trading/impl/simulated_execution_handler.py` | Simulates fills; emits `FillEvent` |
| `Backtester` | `trading/backtester.py` | Owns the event queue; drives the main loop |

### Event types

```
BarBundleEvent    timestamp, bars: dict[symbol → TickEvent]
SignalBundleEvent timestamp, signals: dict[symbol → SignalEvent]
SignalEvent       symbol, timestamp, signal: float  [value type, not queued]
                    signal > 0  long  (fraction of nominal allocated to this symbol)
                    signal = 0  exit / flat
                    signal < 0  short (clamped to 0 by SimplePortfolio — no shorts)
                    sum of signals across one bundle should be ≤ 1
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

# 4. Run the backtest
python run_backtest.py

# 5. Visualize results (select the "vibe-quant" kernel in the notebook)
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
SYMBOLS         = ["AAPL", "MSFT"]   # symbols to fetch and trade
START           = "2020-01-01"        # backtest start date (Yahoo data)
END             = "2022-01-01"        # backtest end date
INITIAL_CAPITAL = 10_000.0
FAST_WINDOW     = 10      # SMA crossover fast period
SLOW_WINDOW     = 30      # SMA crossover slow period
COMMISSION      = 1.0     # dollars per fill
SLIPPAGE_PCT    = 0.0005  # 0.05% per fill
```

## CSV format

When using `MultiCSVDataHandler` instead of `YahooDataHandler`, each symbol CSV must have these columns (header required):

```
timestamp,open,high,low,close,volume
2020-01-02,150.0,151.2,149.3,150.8,1200000
...
```

Default date format is `%Y-%m-%d`. Override via `date_format` on `MultiCSVDataHandler`. Missing bars for a given timestamp are zero-filled automatically.

## Implementing a custom strategy

Create a new file in `strategies/` and subclass `Strategy`:

```python
# strategies/my_strategy.py
from dataclasses import dataclass
from trading.base.strategy import Strategy
from trading.base.strategy_params import StrategyParams
from trading.events import BarBundleEvent, SignalBundleEvent, SignalEvent

@dataclass
class MyStrategyParams(StrategyParams):
    symbols:  list[str]
    lookback: int   = 20
    nominal:  float = 5_000.0   # cash this strategy controls

class MyStrategy(Strategy):
    def _init(self, strategy_params: StrategyParams):
        self._lookback = strategy_params.lookback  # type: ignore[attr-defined]

    def calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None:
        active = []
        for symbol in self.symbols:
            bars = self.get_bars(symbol, self._lookback)
            if len(bars) < self._lookback:
                continue
            # ... decide if symbol should be long ...
            # active.append(symbol)

        if not active:
            return None

        # Normalise so positive weights sum to 1
        weight = 1.0 / len(active)
        signals = {
            s: SignalEvent(symbol=s, timestamp=event.timestamp,
                           signal=weight if s in active else 0.0)
            for s in self.symbols
        }
        return SignalBundleEvent(timestamp=event.timestamp, signals=signals)
```

`signal` is a float target weight: `> 0` = long, `0` = exit, `< 0` = short (blocked by portfolio). Weights across one bundle should sum to ≤ 1 so the strategy never over-allocates its nominal.

Then register it in `run_backtest.py`:

```python
from strategies.my_strategy import MyStrategy, MyStrategyParams
strategy.add(MyStrategy, MyStrategyParams(symbols=SYMBOLS, lookback=20, nominal=5_000.0))
```

## Project structure

```
.
├── trading/
│   ├── base/
│   │   ├── data.py                     # DataHandler ABC
│   │   ├── strategy.py                 # StrategyBase, StrategySignalGenerator, Strategy ABCs
│   │   ├── strategy_params.py          # StrategyParams base dataclass
│   │   ├── portfolio.py                # Portfolio ABC
│   │   └── execution.py               # ExecutionHandler ABC
│   ├── impl/
│   │   ├── multi_csv_data_handler.py   # CSV-backed data handler
│   │   ├── yahoo_data_handler.py       # Yahoo Finance data handler
│   │   ├── strategy_container.py       # Holds + dispatches to strategies
│   │   ├── simple_portfolio.py         # SimplePortfolio
│   │   └── simulated_execution_handler.py
│   ├── events.py                       # all event dataclasses + EventType enum
│   └── backtester.py                   # event loop
├── strategies/
│   └── sma_crossover_strategy.py       # SMACrossoverStrategy
├── external/
│   └── yahoo.py                        # fetch_daily_bars (yfinance wrapper)
├── data/
│   ├── AAPL.csv
│   └── MSFT.csv
├── results/
│   └── equity_curve.csv
├── tests/
├── run_backtest.py                      # entry point + configuration
├── plot_results.ipynb                   # equity curve, drawdown, trade markers
└── requirements.txt
```

## Requirements

Python 3.10+ (uses `match` statement).

| Package | Purpose |
|---|---|
| `yfinance` | `YahooDataHandler` — fetches OHLCV data from Yahoo Finance |
| `matplotlib>=3.7` | `plot_results.ipynb` — equity curve, drawdown, trade markers |
| `ipykernel` | Registers the venv as a Jupyter kernel (`vibe-quant`) |
| `pytest>=7.0` | Test suite (`tests/`) |
| `pandas>=2.0` | Optional — cleaner post-run analysis (not used yet) |

Install: `pip install -r requirements.txt`

## Extension points

- **RiskManager** — insert between Portfolio and Execution to enforce max drawdown / position limits
- **Live trading** — replace `YahooDataHandler` with a streaming data source; replace `SimulatedExecutionHandler` with a broker API client
- **PerformanceAnalyzer** — consume the equity curve to compute Sharpe ratio, max drawdown, CAGR
