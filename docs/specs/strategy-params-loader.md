# Strategy Params JSON Loader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use subagent-driven-development (recommended) or implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move strategy-specific parameters out of `run_backtest.py` into JSON files under `strategy_params/`, loaded via a new `StrategyParamsLoader` ABC and `JsonStrategyParamsLoader`. Multiple strategies can share a class; each is identified by a unique name.

**Architecture:** `strategy_params/params.json` maps **strategy name** → **fully-qualified Strategy class path**. The loader reads this registry at init, derives the `StrategyParams` subclass via the `<StrategyClass>Params` convention, and always injects the registry key as `StrategyParams.name`. Per-strategy files are named `<strategy_name>.json` (no `name` field needed inside — the loader injects it). `load_all()` returns `(StrategyClass, StrategyParams)` pairs for `run_backtest.py` to iterate over.

**Tech Stack:** Python stdlib only (`json`, `pathlib`, `importlib`). No new dependencies.

---

## Design decisions

### `StrategyParams.name` becomes required

`name` is moved to a mandatory field (no default) so every `StrategyParams` instance always carries a unique identifier:

```python
@dataclass
class StrategyParams:
    symbols: list[str]
    name:    str
    nominal: float = 1.0
```

`SMACrossoverStrategyParams` removes the `symbols` re-declaration (it caused fragile dataclass field ordering; `symbols` is already inherited):

```python
@dataclass
class SMACrossoverStrategyParams(StrategyParams):
    fast: int = 10
    slow: int = 30
```

Existing tests that construct params without `name` will need to be updated.

### Registry format

`strategy_params/params.json`:
```json
{
  "sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"
}
```

- Key = strategy name (= JSON filename, must be unique)
- Value = fully-qualified Strategy class path (multiple keys can point to the same class)

### File naming

```
strategy_params/
├── params.json
└── sma_10_30.json      ← named by strategy name, not class name
```

`sma_10_30.json` does **not** include a `name` field — the loader injects it from the registry key:
```json
{
  "symbols": ["AAPL", "MSFT"],
  "fast": 10,
  "slow": 30,
  "nominal": 1.0
}
```

---

## File Map

| Action | Path | Purpose |
|--------|------|---------|
| Modify | `trading/base/strategy_params.py` | Make `name` required; move before `nominal` |
| Modify | `strategies/sma_crossover_strategy.py` | Remove `symbols` re-declaration from `SMACrossoverStrategyParams` |
| Modify | `tests/test_strategy.py` | Add `name=` to all `SMACrossoverStrategyParams(...)` calls |
| Modify | `tests/test_strategy_container.py` | Add `name=` to all `StrategyParams(...)` / `SMACrossoverStrategyParams(...)` calls |
| Create | `trading/base/strategy_params_loader.py` | ABC: abstract `load(strategy_name)` and `load_all()` |
| Create | `trading/impl/json_strategy_params_loader.py` | Concrete: registry-based loader with name injection |
| Modify | `trading/base/__init__.py` | Export `StrategyParamsLoader` (also add missing `StrategyParams` import) |
| Modify | `trading/impl/__init__.py` | Export `JsonStrategyParamsLoader` |
| Create | `strategy_params/params.json` | Registry |
| Create | `strategy_params/sma_10_30.json` | Example SMA params |
| Create | `tests/test_json_strategy_params_loader.py` | Loader tests |
| Modify | `run_backtest.py` | Remove `FAST_WINDOW`/`SLOW_WINDOW`/`SYMBOLS`; use `loader.load_all()` |

---

## Task 1: Make `StrategyParams.name` required

**Files:**
- Modify: `trading/base/strategy_params.py`
- Modify: `strategies/sma_crossover_strategy.py`
- Modify: `tests/test_strategy.py`
- Modify: `tests/test_strategy_container.py`

- [ ] **Step 1: Update `StrategyParams`**

Replace `trading/base/strategy_params.py`:

```python
from dataclasses import dataclass


@dataclass
class StrategyParams:
    symbols: list[str]
    name:    str
    nominal: float = 1.0
```

- [ ] **Step 2: Update `SMACrossoverStrategyParams`**

In `strategies/sma_crossover_strategy.py`, replace the dataclass definition:

```python
@dataclass
class SMACrossoverStrategyParams(StrategyParams):
    fast: int = 10
    slow: int = 30
```

(Remove the `symbols: list[str]` re-declaration — it is inherited from `StrategyParams`.)

- [ ] **Step 3: Run the test suite to see exactly what breaks**

```bash
pytest tests/ -v --ignore=tests/test_yahoo_external.py 2>&1 | head -60
```
Expected: failures in `test_strategy.py` and `test_strategy_container.py` wherever `StrategyParams(symbols=...)` or `SMACrossoverStrategyParams(symbols=...)` is called without `name`.

- [ ] **Step 4: Fix `tests/test_strategy.py`**

Add `name="..."` to every params construction in the file. For example, every occurrence of:
```python
SMACrossoverStrategyParams(symbols=["AAPL"], fast=10, slow=30)
```
becomes:
```python
SMACrossoverStrategyParams(symbols=["AAPL"], name="test_sma", fast=10, slow=30)
```

Use `name="test_sma"` (or any non-empty string) for all test instances.

- [ ] **Step 5: Fix `tests/test_strategy_container.py`**

Add `name="..."` to every `StrategyParams(...)` or `SMACrossoverStrategyParams(...)` call. For unique IDs, use distinct names where the container is tested for ID uniqueness (tests checking `_ids` or `strategy_id`). For all others, any non-empty unique string per test function is fine.

- [ ] **Step 6: Run the full test suite**

```bash
pytest tests/ -v --ignore=tests/test_yahoo_external.py
```
Expected: all tests PASS.

- [ ] **Step 7: Commit**

```bash
git add trading/base/strategy_params.py strategies/sma_crossover_strategy.py tests/test_strategy.py tests/test_strategy_container.py
git commit -m "feat: make StrategyParams.name a required field"
```

---

## Task 2: `StrategyParamsLoader` ABC

**Files:**
- Create: `trading/base/strategy_params_loader.py`
- Modify: `trading/base/__init__.py`
- Test: `tests/test_json_strategy_params_loader.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_json_strategy_params_loader.py`:

```python
import pytest
from trading.base.strategy_params_loader import StrategyParamsLoader
from trading.base.strategy_params import StrategyParams


def test_strategy_params_loader_is_abstract():
    with pytest.raises(TypeError):
        StrategyParamsLoader()


class _ConcreteLoader(StrategyParamsLoader):
    def load(self, strategy_name: str) -> StrategyParams:
        return StrategyParams(symbols=["AAPL"], name=strategy_name)

    def load_all(self):
        return []


def test_concrete_subclass_is_instantiable():
    loader = _ConcreteLoader()
    result = loader.load("my_strategy")
    assert isinstance(result, StrategyParams)
    assert result.name == "my_strategy"


def test_concrete_load_all_returns_list():
    assert _ConcreteLoader().load_all() == []
```

- [ ] **Step 2: Run to verify it fails**

```bash
pytest tests/test_json_strategy_params_loader.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Create the ABC**

Create `trading/base/strategy_params_loader.py`:

```python
from abc import ABC, abstractmethod

from .strategy_params import StrategyParams


class StrategyParamsLoader(ABC):
    @abstractmethod
    def load(self, strategy_name: str) -> StrategyParams:
        """Load and return StrategyParams for the given strategy name."""
        ...

    @abstractmethod
    def load_all(self) -> list[tuple[type, StrategyParams]]:
        """Return (StrategyClass, StrategyParams) for every registered strategy."""
        ...
```

- [ ] **Step 4: Update `trading/base/__init__.py`**

```python
from .data                   import DataHandler
from .execution              import ExecutionHandler
from .portfolio              import Portfolio
from .result_writer          import BacktestResultWriter
from .strategy               import Strategy, StrategyBase, StrategySignalGenerator
from .strategy_params        import StrategyParams
from .strategy_params_loader import StrategyParamsLoader

__all__ = [
    "BacktestResultWriter",
    "DataHandler",
    "ExecutionHandler",
    "Portfolio",
    "Strategy",
    "StrategyBase",
    "StrategySignalGenerator",
    "StrategyParams",
    "StrategyParamsLoader",
]
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_json_strategy_params_loader.py -v
```
Expected: 3 PASSED.

- [ ] **Step 6: Commit**

```bash
git add trading/base/strategy_params_loader.py trading/base/__init__.py tests/test_json_strategy_params_loader.py
git commit -m "feat: add StrategyParamsLoader ABC"
```

---

## Task 3: `JsonStrategyParamsLoader` Implementation

**Files:**
- Create: `trading/impl/json_strategy_params_loader.py`
- Modify: `trading/impl/__init__.py`
- Test: `tests/test_json_strategy_params_loader.py` (extend)

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_json_strategy_params_loader.py`:

```python
import json
from pathlib import Path

from trading.impl.json_strategy_params_loader import JsonStrategyParamsLoader
from strategies.sma_crossover_strategy import SMACrossoverStrategy, SMACrossoverStrategyParams


@pytest.fixture
def params_dir(tmp_path: Path) -> Path:
    return tmp_path


def _setup_dir(params_dir: Path, registry: dict, strategies: dict[str, dict]) -> None:
    (params_dir / "params.json").write_text(json.dumps(registry))
    for name, data in strategies.items():
        (params_dir / f"{name}.json").write_text(json.dumps(data))


def test_load_injects_strategy_name(params_dir):
    _setup_dir(
        params_dir,
        registry={"sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"},
        strategies={"sma_10_30": {"symbols": ["AAPL"], "fast": 10, "slow": 30, "nominal": 1.0}},
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    result = loader.load("sma_10_30")
    assert isinstance(result, SMACrossoverStrategyParams)
    assert result.name == "sma_10_30"
    assert result.fast == 10
    assert result.slow == 30


def test_load_all_returns_strategy_class_and_params(params_dir):
    _setup_dir(
        params_dir,
        registry={"sma_fast": "strategies.sma_crossover_strategy.SMACrossoverStrategy"},
        strategies={"sma_fast": {"symbols": ["MSFT"], "fast": 5, "slow": 20, "nominal": 0.5}},
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    all_strategies = loader.load_all()
    assert len(all_strategies) == 1
    strategy_cls, params = all_strategies[0]
    assert strategy_cls is SMACrossoverStrategy
    assert isinstance(params, SMACrossoverStrategyParams)
    assert params.name == "sma_fast"
    assert params.symbols == ["MSFT"]


def test_two_strategies_same_class(params_dir):
    _setup_dir(
        params_dir,
        registry={
            "sma_a": "strategies.sma_crossover_strategy.SMACrossoverStrategy",
            "sma_b": "strategies.sma_crossover_strategy.SMACrossoverStrategy",
        },
        strategies={
            "sma_a": {"symbols": ["AAPL"], "fast": 5,  "slow": 15, "nominal": 1.0},
            "sma_b": {"symbols": ["MSFT"], "fast": 20, "slow": 60, "nominal": 1.0},
        },
    )
    loader = JsonStrategyParamsLoader(str(params_dir))
    all_strategies = loader.load_all()
    assert len(all_strategies) == 2
    names = {params.name for _, params in all_strategies}
    assert names == {"sma_a", "sma_b"}


def test_load_missing_file_raises(params_dir):
    (params_dir / "params.json").write_text(json.dumps(
        {"sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"}
    ))
    loader = JsonStrategyParamsLoader(str(params_dir))
    with pytest.raises(FileNotFoundError):
        loader.load("sma_10_30")


def test_load_unknown_strategy_raises(params_dir):
    (params_dir / "params.json").write_text(json.dumps({}))
    loader = JsonStrategyParamsLoader(str(params_dir))
    with pytest.raises(KeyError):
        loader.load("nonexistent")


def test_missing_params_json_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        JsonStrategyParamsLoader(str(tmp_path))
```

- [ ] **Step 2: Run to verify they fail**

```bash
pytest tests/test_json_strategy_params_loader.py -v
```
Expected: `ImportError`.

- [ ] **Step 3: Implement `JsonStrategyParamsLoader`**

Create `trading/impl/json_strategy_params_loader.py`:

```python
import importlib
import json
from pathlib import Path

from trading.base.strategy_params import StrategyParams
from trading.base.strategy_params_loader import StrategyParamsLoader


class JsonStrategyParamsLoader(StrategyParamsLoader):
    """
    Reads params.json at init. Format:
        { "<strategy_name>": "<module.path.StrategyClass>", ... }

    Per-strategy params live in <params_dir>/<strategy_name>.json.
    The StrategyParams subclass is resolved by appending "Params" to the class name.
    The loader injects strategy_name as StrategyParams.name (not in the JSON file).
    """

    def __init__(self, params_dir: str) -> None:
        self._params_dir = Path(params_dir)
        registry_path = self._params_dir / "params.json"
        with open(registry_path) as f:
            self._registry: dict[str, str] = json.load(f)

    def _resolve(self, strategy_name: str) -> tuple[type, type[StrategyParams]]:
        full_path = self._registry[strategy_name]           # KeyError if unknown
        module_path, class_name = full_path.rsplit(".", 1)
        module = importlib.import_module(module_path)
        strategy_cls = getattr(module, class_name)
        params_cls   = getattr(module, class_name + "Params")
        return strategy_cls, params_cls

    def load(self, strategy_name: str) -> StrategyParams:
        _, params_cls = self._resolve(strategy_name)
        path = self._params_dir / f"{strategy_name}.json"
        with open(path) as f:                               # FileNotFoundError if missing
            data = json.load(f)
        data["name"] = strategy_name                        # inject; not stored in JSON
        return params_cls(**data)

    def load_all(self) -> list[tuple[type, StrategyParams]]:
        return [
            (strategy_cls, self.load(name))
            for name, (strategy_cls, _) in
            ((n, self._resolve(n)) for n in self._registry)
        ]
```

- [ ] **Step 4: Update `trading/impl/__init__.py`**

```python
from .json_strategy_params_loader import JsonStrategyParamsLoader
from .multi_csv_data_handler      import MultiCSVDataHandler
from .simulated_execution_handler import SimulatedExecutionHandler
from .simple_portfolio            import SimplePortfolio
from .strategy_container          import StrategyContainer
from .yahoo_data_handler          import YahooDataHandler

__all__ = [
    "JsonStrategyParamsLoader",
    "MultiCSVDataHandler",
    "SimulatedExecutionHandler",
    "SimplePortfolio",
    "StrategyContainer",
    "YahooDataHandler",
]
```

- [ ] **Step 5: Run all loader tests**

```bash
pytest tests/test_json_strategy_params_loader.py -v
```
Expected: 9 PASSED (3 from Task 2 + 6 new).

- [ ] **Step 6: Commit**

```bash
git add trading/impl/json_strategy_params_loader.py trading/impl/__init__.py tests/test_json_strategy_params_loader.py
git commit -m "feat: implement JsonStrategyParamsLoader with name injection"
```

---

## Task 4: JSON files + wire into `run_backtest.py`

**Files:**
- Create: `strategy_params/params.json`
- Create: `strategy_params/sma_10_30.json`
- Modify: `run_backtest.py`

- [ ] **Step 1: Create `strategy_params/params.json`**

```json
{
  "sma_10_30": "strategies.sma_crossover_strategy.SMACrossoverStrategy"
}
```

- [ ] **Step 2: Create `strategy_params/sma_10_30.json`**

```json
{
  "symbols": ["AAPL", "MSFT"],
  "fast": 10,
  "slow": 30,
  "nominal": 1.0
}
```

- [ ] **Step 3: Update `run_backtest.py`**

```python
"""
Entry point — wire all components together and run the backtest.
Modify START, END, INITIAL_CAPITAL, COMMISSION_PCT, SLIPPAGE_PCT,
MARKET_IMPACT_ETA to experiment. Strategy-specific params (symbols,
windows, etc.) live in strategy_params/<strategy_name>.json.
Register new strategies in strategy_params/params.json.
"""
import queue

from analysis.result_writer import DefaultResultWriter
from external.yahoo import fetch_daily_bars
from trading.backtester import Backtester
from trading.impl import (
    JsonStrategyParamsLoader,
    SimulatedExecutionHandler,
    SimplePortfolio,
    StrategyContainer,
    YahooDataHandler,
)

# --- Backtest Configuration --------------------------------------------------
START              = "2020-01-01"
END                = "2022-01-01"
INITIAL_CAPITAL    = 10_000.0
COMMISSION_PCT     = 0.001   # 0.1% of trade value per fill
SLIPPAGE_PCT       = 0.0005  # fixed spread floor (one-way minimum cost)
MARKET_IMPACT_ETA  = 0.1     # square-root impact coefficient (Almgren et al.)
RESULTS_DIR        = "results"
RESULTS_FORMAT     = "parquet"  # "parquet" or "csv"
# -----------------------------------------------------------------------------

events   = queue.Queue()
data     = None  # resolved after strategy symbols are known

loader   = JsonStrategyParamsLoader("strategy_params")
strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
for strategy_cls, params in loader.load_all():
    strategy.add(strategy_cls, params)

symbols   = strategy.symbols
data      = YahooDataHandler(events.put, symbols, start=START, end=END, fetch=fetch_daily_bars)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, symbols, initial_capital=INITIAL_CAPITAL)
execution = SimulatedExecutionHandler(
    events.put,
    commission_pct    = COMMISSION_PCT,
    slippage_pct      = SLIPPAGE_PCT,
    market_impact_eta = MARKET_IMPACT_ETA,
)

writer = DefaultResultWriter(
    initial_capital = INITIAL_CAPITAL,
    symbol_bars     = data.symbol_bars,
    results_dir     = RESULTS_DIR,
    fmt             = RESULTS_FORMAT,
)

bt = Backtester(events, data, strategy, portfolio, execution, result_writer=writer)
bt.run()
```

- [ ] **Step 4: Run the full test suite**

```bash
pytest tests/ -v --ignore=tests/test_yahoo_external.py
```
Expected: all tests PASS.

- [ ] **Step 5: Smoke-test end-to-end**

```bash
python run_backtest.py
```
Expected: backtest completes, `results/` files written.

- [ ] **Step 6: Commit**

```bash
git add strategy_params/params.json strategy_params/sma_10_30.json run_backtest.py
git commit -m "feat: load strategy params from JSON; remove FAST_WINDOW/SLOW_WINDOW/SYMBOLS from run_backtest"
```
