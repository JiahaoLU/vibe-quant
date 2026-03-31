# Strategy Performance Tracking Design

**Date:** 2026-03-31
**Status:** Approved

## Overview

Track realized PnL per strategy using notional attribution. When multiple strategies contribute to a combined signal for a symbol, each fill's PnL is apportioned by the fraction of the combined signal that each strategy contributed. No virtual books, no isolated portfolios — a single shared portfolio with attribution metadata flowing through the event.

## Events

`SignalBundleEvent` is demoted from a queued event to an internal value type (like `SignalEvent` and `TickEvent`). A new `StrategyBundleEvent` replaces it in the queue.

```python
class EventType(Enum):
    BAR_BUNDLE       = auto()
    STRATEGY_BUNDLE  = auto()   # replaces SIGNAL_BUNDLE
    ORDER            = auto()
    FILL             = auto()

@dataclass
class StrategyBundleEvent(Event):
    timestamp:    datetime
    combined:     dict[str, SignalEvent]        # aggregated signal per symbol
    per_strategy: dict[str, dict[str, float]]  # strategy_id → symbol → fractional weight (sums to 1.0 per symbol)
    type: EventType = field(default=EventType.STRATEGY_BUNDLE, init=False)
```

`SignalBundleEvent` remains defined in `events.py` for use as a carry-forward value inside `StrategyContainer`, but is no longer enqueued.

## Strategy Naming

`StrategyParams` gains an optional `name: str = ""` field. `StrategyContainer.add()` uses it as the strategy id, falling back to `f"{strategy_class.__name__}_{index}"` if empty. This keeps the existing `add()` call signature backward-compatible.

## StrategyContainer

Aggregation logic is unchanged. After computing `combined`, one additional pass computes `per_strategy`:

```
weight_i = nominal_i / total_nominal
per_strategy[strategy_id][symbol] = weight_i * carried_i[symbol] / combined[symbol]
```

This fraction represents strategy `i`'s share of the combined signal for each symbol. It sums to 1.0 across strategies per symbol when `combined[symbol] != 0`. Symbols where `combined[symbol] == 0` are omitted from `per_strategy` (no fill will occur).

The container emits a `StrategyBundleEvent` instead of `SignalBundleEvent`.

## SimplePortfolio

### Fill path (unchanged)

`on_signal` stores the pending `StrategyBundleEvent`. `fill_pending_orders` reads `event.combined` to compute target quantities — identical to today's `event.signals`. No change to order logic.

### PnL attribution (new)

`on_fill` apportions each fill's cash impact across strategies using the same sign convention as the portfolio's cash ledger (`multiplier = +1` for BUY, `-1` for SELL):

```
# matches: self._cash -= multiplier * fill_price * quantity + commission
fill_cash_impact = multiplier * fill_price * quantity + commission   # positive = cash outflow (cost)
strategy_share   = per_strategy.get(strategy_id, {}).get(symbol, 0.0)
realized_pnl[strategy_id] -= strategy_share * fill_cash_impact      # negate so profit is positive
```

Net effect: buying reduces `realized_pnl`, selling at a higher price restores it. Commission always reduces it. The sum across all strategies equals total cash spent/received. `_strategy_realized_pnl: dict[str, float]` accumulates across fills. Unrealized PnL is not tracked per strategy.

### Equity curve

Each equity curve entry gains a `strategy_pnl` key:

```python
{
    "timestamp":    event.timestamp,
    "cash":         self._cash,
    "holdings":     dict(self._holdings),
    "market_value": market_value,
    "equity":       self._cash + market_value,
    "strategy_pnl": dict(self._strategy_realized_pnl),  # snapshot at this fill
}
```

A `strategy_pnl` property returns the same list for external access.

## Backtester

One change: `SIGNAL_BUNDLE` case renamed to `STRATEGY_BUNDLE` in the match block. Both the main loop and the drain loop are updated.

## Base Class

`trading/base/portfolio.py`: `on_signal` signature updated from `SignalBundleEvent` to `StrategyBundleEvent`.

## run_backtest.py

- Exports a second CSV `results/strategy_pnl.csv` with columns: `timestamp`, one column per strategy id, values are cumulative realized PnL at that fill event.
- Prints a per-strategy realized PnL summary after the run.

## Files Changed

| File | Change |
|---|---|
| `trading/events.py` | Add `STRATEGY_BUNDLE`, `StrategyBundleEvent`; `SignalBundleEvent` becomes value-only |
| `trading/base/strategy_params.py` | Add `name: str = ""` |
| `trading/impl/strategy_container.py` | Emit `StrategyBundleEvent` with `combined` + `per_strategy` |
| `trading/base/portfolio.py` | Update `on_signal` signature |
| `trading/impl/simple_portfolio.py` | Read `combined`, apportion fills, track `_strategy_realized_pnl` |
| `trading/backtester.py` | `SIGNAL_BUNDLE` → `STRATEGY_BUNDLE` |
| `run_backtest.py` | Export `strategy_pnl.csv`, print per-strategy summary |

## Out of Scope

- Unrealized PnL per strategy (requires lot-level attribution)
- Short positions (already prohibited by `SimplePortfolio`)
- Per-strategy drawdown or Sharpe metrics (post-processing concern)
