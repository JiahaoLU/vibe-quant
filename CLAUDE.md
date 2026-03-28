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

- **No direct cross-component calls.** All component communication goes through the `emit: Callable[[Event], None]` callable injected at construction. The concrete queue is owned by `run_backtest.py` and `Backtester`; components never import or reference `queue.Queue` directly. `Portfolio` and `Strategy` both receive a `get_bars: Callable[[str, int], list[TickEvent]]` callable instead of a full `DataHandler` reference.
- **Event ownership:** each component owns exactly one stage of the pipeline. Strategy never touches orders. Portfolio never touches indicators.
- **ABCs are load-bearing.** `DataHandler`, `StrategyBase`, `Strategy`, `Portfolio`, `ExecutionHandler` are abstract base classes in `trading/base/`. `StrategyBase` defines the shared wiring; `Strategy` adds the researcher-facing `calculate_signals` interface. Concrete implementations live in `trading/impl/`.
- **No pandas in the hot loop.** The event loop operates on plain Python dicts and lists. Pandas is only for post-run analysis.

## Adding a new strategy

1. Create `trading/impl/my_strategy.py`; subclass `Strategy` from `trading.base.strategy`
2. Implement `calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None` — return a `SignalBundleEvent` when signals fire, `None` otherwise
3. Accept `symbols: list[str]` (and any other strategy-specific params) in the constructor; call `super().__init__(emit, get_bars)` — `emit` and `get_bars` are injected by `StrategyContainer` automatically
4. Call `self.get_bars(symbol, n)` to retrieve bar history — no DataHandler import needed
5. Do **not** call `self._emit()` directly — return the bundle from `calculate_signals`; `get_signals` (inherited from `Strategy`) handles emission
6. Export it from `trading/impl/__init__.py`
7. Register it in `run_backtest.py`:

   ```python
   strategy = StrategyContainer(events.put, data.get_latest_bars)
   strategy.add(MyStrategy, symbols=SYMBOLS)
   ```

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
