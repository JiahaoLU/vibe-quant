# Repository Guidelines

## Project Structure & Module Organization
- `trading/` contains abstract bases (`base/`), concrete implementations (`impl/`), event dataclasses, and `backtester.py`; `run_backtest.py` wires them into the event loop.
- `strategies/` is the extension point for signal generators and their `StrategyParams`.
- `external/` holds helpers such as the `yfinance` wrapper, while `data/` stores CSV samples used by `MultiCSVDataHandler`.
- `results/` gathers the equity curves, metrics, and charts that `analysis/plot_results.ipynb` visualizes; `logs/trades.db` is the live-session trade log visualised by `analysis/plot_trades.ipynb`; other notebooks, reports, and drafting notes live under `analysis/` or `docs/`.
- `tests/` mirrors the trading modules with `test_*.py` files and covers the backtester, portfolio, execution handler, data handlers, and container logic.

## Build, Test, and Development Commands
- `python3 -m venv .venv` + `source .venv/bin/activate` → create and enter the isolated environment.
- `pip install -r requirements.txt` → install pinned dependencies (`yfinance`, `pandas`, `pytest`, `matplotlib`, etc.).
- `python -m ipykernel install --user --name=vibe-quant` → register the kernel that the analysis notebooks reference.
- `python run_backtest.py` → execute the event-driven engine with the tunables defined at the top of that file.
- `python -m pytest` → run the unit suite; `pytest.ini` already adds `-m "not integration"` to keep integration work opt-in.
- `jupyter notebook analysis/plot_results.ipynb` → visualize the CSV/jpg files in `results/`.
- `jupyter notebook analysis/plot_trades.ipynb` → visualize the SQLite trade log in `logs/trades.db`.

## Architecture rules

- **No direct cross-component calls.** All component communication goes through the `emit: Callable[[Event], None]` callable injected at construction. The concrete queue is owned by `run_backtest.py` and `Backtester`; components never import or reference `queue.Queue` directly. `Portfolio` and `StrategyContainer` receive `emit`; `Strategy` and `Portfolio` receive a `get_bars: Callable[[str, int], list[TickEvent]]` callable instead of a full `DataHandler` reference. `Strategy` does **not** receive `emit` — it returns bundles from `calculate_signals` and the container aggregates them.
- **Event ownership:** each component owns exactly one stage of the pipeline. Strategy never touches orders. Portfolio never touches indicators.
- **ABCs are load-bearing.** `DataHandler`, `StrategyBase`, `StrategySignalGenerator`, `Strategy`, `Portfolio`, `ExecutionHandler` are abstract base classes in `trading/base/`. `StrategyBase` provides `get_bars` injection and the abstract `symbols` property; `StrategySignalGenerator` adds the abstract `emit` and `get_signals` interface (implemented by `StrategyContainer`); `Strategy` adds the researcher-facing `calculate_signals` and `on_get_signal` hook. Concrete implementations live in `trading/impl/`.
- **No pandas in the hot loop.** The event loop operates on plain Python dicts and lists. Pandas is only for post-run analysis.

## Coding Style & Naming Conventions
Use four-space indentation, `snake_case.py` for modules, and `PascalCase` for classes/dataclasses. Keep vars/methods `snake_case`, prefix private members with `_`, and favor explicit type hints (`dict[str, float]`, `Callable`, `Foo | None`). Group imports by stdlib, third party, and local modules.

## Testing Guidelines
Place tests under `tests/` with `test_*.py` names and run `python -m pytest` from the repo root while the virtual environment is active. Integration work must add explicit markers because `pytest.ini` skips the `integration` group by default.

## Commit & Pull Request Guidelines
Follow the existing `type: short-description` pattern (`feat: ...`, `fix: ...`) with lowercase types and, when relevant, reference issues/PRs in the body. PRs should summarize the change, document the commands/tests you ran, and note any configuration updates; share exports/screenshots only for visual artifacts.

## What not to do
- Do not add pandas/numpy/matplotlib imports inside `trading/` modules — keep the engine dependency-free.
- Do not have Strategy emit OrderEvents directly — signals and orders are intentionally decoupled so position sizing lives in Portfolio.
- Do not skip the ABC layer when adding new data sources or execution handlers — the abstractions are what makes the live/backtest swap possible.
