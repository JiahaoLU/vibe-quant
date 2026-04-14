# Event-Driven Trading & Backtesting POC

A minimal, extensible event-driven trading engine and backtester written in pure Python (stdlib only).

## Architecture

All components communicate through an `emit: Callable[[Event], None]` injected at construction — no direct cross-component calls. The concrete `queue.Queue` is owned by `run_backtest.py` and `Backtester` only.

```
DataHandler → BarBundleEvent → StrategyContainer → SignalBundleEvent → [RiskGuard] → Portfolio → OrderEvent → ExecutionHandler → FillEvent → Portfolio
```

| Component | File | Responsibility |
|---|---|---|
| `DataHandler` | `trading/impl/data_handler/multi_csv_data_handler.py` / `yahoo_data_handler.py` / `alpaca_data_handler.py` | Emits `BarBundleEvent`; CSV/Yahoo replay historical bars; Alpaca streams live bars |
| `StrategyContainer` | `trading/impl/strategy_signal_generator/strategy_container.py` | Aggregates weighted signals from all strategies; emits one `SignalBundleEvent` per bar |
| `Strategy` | `strategies/sma_crossover_strategy.py` | Consumes bar bundles; returns `SignalBundleEvent` with normalised float weights |
| `RiskGuard` | `trading/impl/risk_guard/risk_guard.py` | Pre-trade check: enforces daily loss limit and per-symbol position cap; returns `None` to halt |
| `Portfolio` | `trading/impl/portfolio/simple_portfolio.py` | Rebalances to target weights; emits `OrderEvent`; tracks equity |
| `ExecutionHandler` | `trading/impl/execution_handler/simulated_execution_handler.py` / `live_execution_handler/alpaca_*.py` | Simulates fills (backtest) or routes orders to Alpaca (live/paper); emits `FillEvent` |
| `Backtester` | `trading/backtester.py` | Owns the event queue; drives the main (backtest) loop |
| `LiveRunner` | `trading/live_runner.py` | asyncio loop; reconciles positions on startup, drains fill stream, handles graceful shutdown |
| `PositionReconciler` | `trading/impl/position_reconciler/alpaca_reconciler.py` | Queries broker on startup and calls `portfolio.restore(holdings, cash)` |

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
START              = "2020-01-01"      # backtest start date (Yahoo data)
END                = "2022-01-01"      # backtest end date
INITIAL_CAPITAL    = 10_000.0          # starting portfolio cash
COMMISSION_PCT     = 0.001             # 0.1% of trade value per fill
SLIPPAGE_PCT       = 0.0005            # fixed spread floor (one-way minimum cost)
MARKET_IMPACT_ETA  = 0.1               # square-root impact coefficient
RESULTS_DIR        = "results"         # output directory for backtest artifacts
RESULTS_FORMAT     = "parquet"         # "parquet" or "csv"
```

## Live / paper trading

```bash
# Set credentials (paper and live use the same key pair; MODE controls the endpoint)
export ALPACA_API_KEY=your_key
export ALPACA_SECRET_KEY=your_secret

# Paper trading (default — safe, uses Alpaca paper endpoint)
python run_live.py

# Live trading (real capital — change MODE = "live" in run_live.py first)
python run_live.py
```

Key configuration constants at the top of `run_live.py`:

```python
MODE               = "paper"   # "paper" | "live"
BAR_FREQ           = "1d"      # "1d" daily; "5m" intraday
INITIAL_CAPITAL    = 10_000.0
MAX_DAILY_LOSS_PCT = 0.05      # halt if equity drops 5% from day open
MAX_POSITION_PCT   = 0.20      # cap any single position at 20% of equity
```

On startup `LiveRunner` calls `AlpacaReconciler.hydrate()` which syncs broker positions into the portfolio before the first bar arrives. On SIGINT/SIGTERM it drains any in-flight fills and shuts down cleanly.

Strategy-specific parameters (symbols, windows, etc.) live in `strategy_params/<strategy_name>.json`. Strategies are registered in `strategy_params/params.json`.

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
    lookback: int   = 20
    nominal:  float = 1.0   # relative weight vs other strategies in the same StrategyContainer

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

**`bar_freq`** controls the bar resolution passed to `StrategyParams` (default `"1d"`). Supported values:

| Value | Resolution | Notes |
|---|---|---|
| `"1d"` | Daily | Default; works with `MultiCSVDataHandler` and `YahooDataHandler` |
| `"1h"` | Hourly | Alpaca live/paper only |
| `"1m"` | 1-minute | Alpaca live/paper only |
| `"Nm"` | N-minute (e.g. `"5m"`, `"15m"`) | Alpaca live/paper only; N must be a positive integer |

All strategies in a `StrategyContainer` must use the same resolution class (all daily **or** all intraday). Mixing daily and intraday raises a `ValueError` from `required_freq`. When multiple intraday strategies are present, `required_freq` selects the finest resolution so coarser strategies fire every N bars automatically.

Then register it in `strategy_params/params.json`:

```json
{ "my_strategy": "strategies.my_strategy.MyStrategy" }
```

And create `strategy_params/my_strategy.json`:

```json
{ "symbols": ["AAPL", "MSFT"], "lookback": 20, "nominal": 1.0 }
```

## Project structure

```
.
├── trading/
│   ├── base/
│   │   ├── data.py                     # DataHandler ABC
│   │   ├── strategy.py                 # StrategyBase, StrategySignalGenerator, Strategy ABCs
│   │   ├── strategy_params.py          # StrategyParams base dataclass
│   │   ├── strategy_params_loader.py   # StrategyParamsLoader ABC
│   │   ├── portfolio.py                # Portfolio ABC
│   │   ├── execution.py                # ExecutionHandler ABC
│   │   └── live/
│   │       ├── risk_guard.py           # RiskGuard ABC
│   │       ├── reconciler.py           # PositionReconciler ABC
│   │       └── runner.py               # LiveRunner ABC
│   ├── impl/
│   │   ├── data_handler/
│   │   │   ├── alpaca_data_handler.py          # Alpaca live data handler (async bar streaming)
│   │   │   ├── multi_csv_data_handler.py       # CSV-backed data handler
│   │   │   └── yahoo_data_handler.py           # Yahoo Finance data handler
│   │   ├── execution_handler/
│   │   │   └── simulated_execution_handler.py  # Simulates fills for backtesting
│   │   ├── live_execution_handler/
│   │   │   ├── alpaca_execution_handler.py     # Alpaca live order routing (real capital)
│   │   │   └── alpaca_paper_execution_handler.py  # Alpaca paper endpoint
│   │   ├── portfolio/
│   │   │   └── simple_portfolio.py             # SimplePortfolio (supports restore())
│   │   ├── position_reconciler/
│   │   │   └── alpaca_reconciler.py            # Hydrates portfolio from broker on startup
│   │   ├── risk_guard/
│   │   │   └── risk_guard.py                   # Daily loss limit + per-symbol position cap
│   │   ├── strategy_params_loader/
│   │   │   └── json_strategy_params_loader.py  # Registry-based JSON loader
│   │   ├── strategy_signal_generator/
│   │   │   └── strategy_container.py           # Holds + dispatches to strategies
│   │   └── universe_builder/
│   │       └── index_constituents_universe_builder.py
│   ├── events.py                       # all event dataclasses + EventType enum
│   ├── backtester.py                   # event loop (backtest)
│   └── live_runner.py                  # asyncio event loop (live/paper trading)
├── strategy_params/
│   ├── params.json                     # registry: strategy name → Strategy class path
│   ├── sma_10_30.json                  # params for the sma_10_30 strategy instance
│   └── sma_20_50.json                  # params for the sma_20_50 strategy instance
├── strategies/
│   └── sma_crossover_strategy.py       # SMACrossoverStrategy
├── external/
│   ├── alpaca.py                       # Alpaca SDK wrappers (REST + stream)
│   └── yahoo.py                        # fetch_daily_bars (yfinance wrapper)
├── data/
│   ├── AAPL.csv
│   └── MSFT.csv
├── results/
│   └── ...                             # equity_curve, summary_metrics, strategy_pnl, strategy_metrics (csv/parquet + jpg charts)
├── tests/
├── run_backtest.py                      # backtest entry point + configuration
├── run_live.py                          # live/paper trading entry point + configuration
├── plot_results.ipynb                   # equity curve, drawdown, trades, per-strategy metrics & PnL
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
| `pandas>=2.0` | `plot_results.ipynb` — loads result files for display |
| `pyarrow>=14.0` | Parquet result writing (`DefaultResultWriter`) |
| `alpaca-py>=0.13` | `AlpacaDataHandler`, `AlpacaExecutionHandler`, `AlpacaReconciler` — live/paper trading |
| `pytest-asyncio>=0.23` | Async test support for live trading components |

Install: `pip install -r requirements.txt`

## Extension points

- **Custom RiskGuard** — subclass `trading.base.live.risk_guard.RiskGuard`; inject via `SimplePortfolio(risk_guard=...)` to add new pre-trade checks without touching portfolio logic
- **New broker** — implement `PositionReconciler` and a matching `ExecutionHandler`; swap them in `run_live.py` without changing any other component
