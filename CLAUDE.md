# CLAUDE.md

## Project overview

Event-driven trading engine and backtester. Pure Python stdlib — no third-party dependencies in the core engine. Python 3.10+ required (uses `match` statement).

## Running the project

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name=claude-learn
python generate_data.py           # generate data/sample_data.csv
python run_backtest.py            # run backtest, write results/equity_curve.csv
jupyter notebook plot_results.ipynb  # select "claude-learn" kernel
```

## Architecture rules

- **No direct cross-component calls.** All communication goes through the shared `queue.Queue`. Components only call methods on `DataHandler` to read bar history.
- **Event ownership:** each component owns exactly one stage of the pipeline. Strategy never touches orders. Portfolio never touches indicators.
- **ABCs are load-bearing.** `DataHandler`, `Strategy`, `Portfolio`, `ExecutionHandler` are all abstract base classes. Concrete implementations go in the same file as the ABC, named `Multi...`, `Simple...`, `Simulated...`, etc.
- **No pandas in the hot loop.** The event loop operates on plain Python dicts and lists. Pandas is only for post-run analysis.

## Adding a new strategy

1. Create `trading/impl/my_strategy.py`; subclass `Strategy` from `trading.base.strategy`
2. Implement `calculate_signals(self, event: BarBundleEvent) -> None`
3. Accept `symbols: list[str]` in the constructor
4. Read bar history via `self._data.get_latest_bars(symbol, n)` per symbol
5. Emit signals via `self._events.put(SignalBundleEvent(...))` — only when at least one symbol has a signal
6. Export it from `trading/impl/__init__.py`
7. Wire it in `run_backtest.py`

## Adding a new component type (e.g. RiskManager)

1. Define a new `EventType` member in `trading/events.py` if a new event is needed
2. Create the ABC in `trading/base/risk.py`; create the implementation in `trading/impl/risk.py`
3. Export both from their respective `__init__.py`
4. Add a dispatch case to the `match` block in `trading/backtester.py`
5. Wire it in `run_backtest.py`

## Key files

| File | Role |
|---|---|
| `trading/events.py` | Single source of truth for all event dataclasses. Edit this first when changing the data model. |
| `trading/backtester.py` | Central event loop. The `match` block is the only place that routes events to handlers. |
| `trading/base/` | ABCs only — no business logic, no imports from `trading/impl/`. |
| `trading/impl/` | Concrete implementations — always import their ABC from `trading/base/`. |
| `trading/impl/data.py` | `get_latest_bars` deque is load-bearing — strategies depend on it for indicator history. |
| `run_backtest.py` | Wiring point. All configuration constants live here. |
| `plot_results.ipynb` | Visualization only — reads CSVs from `data/` and `results/`, never imports `trading/`. |

## CSV data format

```
timestamp,open,high,low,close,volume   # header required
2020-01-02,150.0,151.2,149.3,150.8,1200000
```

Date format default: `%Y-%m-%d`. Configurable via `date_format` parameter on `MultiCSVDataHandler`. Timestamps are unioned across all symbol CSVs — missing bars are zero-filled.

## What not to do

- Do not add pandas/numpy/matplotlib imports inside `trading/` modules — keep the engine dependency-free.
- Do not have Strategy emit OrderEvents directly — signals and orders are intentionally decoupled so position sizing lives in Portfolio.
- Do not skip the ABC layer when adding new data sources or execution handlers — the abstractions are what makes the live/backtest swap possible.
