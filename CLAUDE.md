# CLAUDE.md

## Project overview

Event-driven trading engine and backtester. Pure Python stdlib — no third-party dependencies in the core engine. Python 3.10+ required (uses `match` statement).

## Running the project

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m ipykernel install --user --name=claude-learn
python run_backtest.py            # run backtest, write results/equity_curve.csv
jupyter notebook plot_results.ipynb  # select "claude-learn" kernel
```

## Architecture rules

- **No direct cross-component calls.** All component communication goes through the `emit: Callable[[Event], None]` callable injected at construction. The concrete queue is owned by `run_backtest.py` and `Backtester`; components never import or reference `queue.Queue` directly. `Portfolio` and `StrategyContainer` receive `emit`; `Strategy` and `Portfolio` receive a `get_bars: Callable[[str, int], list[TickEvent]]` callable instead of a full `DataHandler` reference. `Strategy` does **not** receive `emit` — it returns bundles from `calculate_signals` and the container aggregates them.
- **Event ownership:** each component owns exactly one stage of the pipeline. Strategy never touches orders. Portfolio never touches indicators.
- **ABCs are load-bearing.** `DataHandler`, `StrategyBase`, `StrategySignalGenerator`, `Strategy`, `Portfolio`, `ExecutionHandler` are abstract base classes in `trading/base/`. `StrategyBase` provides `get_bars` injection and the abstract `symbols` property; `StrategySignalGenerator` adds the abstract `emit` and `get_signals` interface (implemented by `StrategyContainer`); `Strategy` adds the researcher-facing `calculate_signals` and `on_get_signal` hook. Concrete implementations live in `trading/impl/`.
- **No pandas in the hot loop.** The event loop operates on plain Python dicts and lists. Pandas is only for post-run analysis.

## Signal model

`SignalEvent.signal` is a `float` target weight in `[-1, 1]`:
- `> 0` — long; the value is the fraction of the strategy's nominal to allocate to this symbol
- `= 0` — exit / flat
- `< 0` — short (currently prohibited by `SimplePortfolio`, which clamps to 0)

**The sum of positive signals across a `SignalBundleEvent` should be ≤ 1** so the strategy never over-allocates its nominal. When multiple symbols are active, divide equally (or by your own weights).

`StrategyContainer` aggregates one bundle per bar by combining all strategies' carry-forward signals weighted by `StrategyParams.nominal`.  `SimplePortfolio` then rebalances to `target_qty = int(signal × initial_capital / price)`.

## Adding a new strategy

1. Create `trading/impl/my_strategy.py`; subclass `Strategy` from `trading.base.strategy`
2. Implement `calculate_signals(self, event: BarBundleEvent) -> SignalBundleEvent | None` — return a `SignalBundleEvent` when signals fire, `None` otherwise
3. Define a `StrategyParams` subclass (e.g. `MyStrategyParams`) in the same file; set `nominal` to the cash amount this strategy should control — this is its weight relative to other strategies in the same `StrategyContainer` (default `1.0` gives equal weight).  `get_bars` is injected by `StrategyContainer` automatically — do **not** override `__init__`
4. Implement `_init(self, strategy_params: StrategyParams)` — extract strategy-specific config here; symbols are available as `self.symbols`
5. Call `self.get_bars(symbol, n)` to retrieve bar history — no DataHandler import needed
6. **Return** the bundle from `calculate_signals`; `Strategy` has no `emit` — `StrategyContainer` calls `calculate_signals` directly and aggregates results before emitting
7. When any position changes, **emit signals for all symbols** with normalised weights (sum of long signals ≤ 1) so the carry-forward in `StrategyContainer` stays consistent
8. Export it from `trading/impl/__init__.py`
9. Register it in `run_backtest.py`:

   ```python
   strategy = StrategyContainer(events.put, data.get_latest_bars)
   strategy.add(MyStrategy, MyStrategyParams(symbols=SYMBOLS, nominal=5000.0, ...))
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
