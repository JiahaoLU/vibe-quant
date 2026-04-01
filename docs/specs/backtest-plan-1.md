# Backtest Infrastructure Gap Analysis

Date: 2026-03-31
Scope: audit of current event-driven backtesting engine against production-grade standards.

---

## Critical Issues (introduce bias or incorrect results)

### 1. Execution timing — look-ahead bias

Signals are computed from the current bar's **close**, orders are immediately filled at that same close (± slippage). For daily data this is impossible: the close price is not known until the bar ends, so the first executable price is the **next bar's open**.

Current flow per bar:
```
close_price known → signal generated → OrderEvent(reference_price=close) → fills at close
```

Correct flow:
```
Day T close → signal generated → pending order stored → Day T+1 open → fill
```

Fix requires: 
1. the yahoo data handler should be extensible for intraday trading (not required currently but in the future)
2. backtester should be extensible for intraday trading (not required currently but in the future). For now, it should at least be aware of end of day. (For now we only have 1 bar per day, so every bar means the end of a day)
3. to handle pending signals generated after close, a pending-order queue in `Portfolio`.
Pending orders should be filled on tomorrow's open. Since we only have 1 bar per day, at day T we fill the signals of day T-1 with day T's open and generate the signals of day T with day T's close.

---

### 2. Equity curve only records on fills, not every bar

`SimplePortfolio.on_fill` appends to `_equity_curve`. If no trade fires for 30 bars, the equity curve has a 30-bar gap. This makes:
- Max drawdown calculation impossible without interpolation
- Daily return series unusable for Sharpe/Sortino computation

Fix: 
introduce a direction = 'HOLD' in OrderEvent. It means quantity to trade is zero. in this case, there is no trade happened, so no commission fees. It will help record a point in equity curve even if no fill. 

---

### 3. Zero-fill contaminates indicator history

When a symbol has no bar at a timestamp, `MultiCSVDataHandler` and `YahooDataHandler` insert a synthetic bar with `close=0`. Those zeros flow into the strategy's `get_bars()` deque and distort SMA calculations silently — no error, wrong signal.

Fix: use skip-and-carry-forward for missing bars; guard indicator logic against sparse data.

---

## Important Issues (missing metrics and controls)

### 4. No performance metrics beyond total return

The only output is final equity and trade count. Missing:

| Metric | Why it matters |
|---|---|
| Sharpe ratio | Risk-adjusted return; standard for strategy comparison |
| Max drawdown | Measures worst-case loss; key for risk management |
| CAGR | Annualised return for multi-year backtests |
| Sortino ratio | Penalises downside volatility only |
| Win rate / profit factor | Trade-level quality |
| Calmar ratio | CAGR / max drawdown |

Fix: a `PerformanceAnalyzer` class that consumes the per-bar equity curve.

---

### 5. No position or leverage limits

`SimplePortfolio` can emit buy orders even if `signal * initial_capital > cash`. The `available_cash` guard prevents over-spending within one signal event, but:
- There's no max single-position size limit
- `_cash` can go slightly negative due to commission on a barely-affordable trade
- No leverage ratio cap

---

### 6. Integer truncation causes systematic under-allocation

```python
target_qty = int(signal * initial_capital / price)
```

`int()` always truncates. For a $10k portfolio at $150/share with `signal=0.5`, target = `int(33.33)` = 33 shares ($4,950 vs. $5,000 target). The undeployed cash compounds over time.

---

### 7. Commission model is flat-dollar only

Real brokers charge a percentage of trade value (e.g. 0.1%). A flat $1 commission is unrealistic for large trades (too cheap) and tiny trades (too expensive). The `ExecutionHandler` interface has no percentage-based option.

---

## Moderate Issues (structural gaps)

### 8. No out-of-sample / walk-forward framework

The entire dataset is used for both development and evaluation. There's no:
- Train / validation / test split enforced by the data handler
- Walk-forward window generator
- Parameter optimization loop with OOS gating

---

### 9. Survivorship bias

Yahoo Finance only returns currently-listed symbols. Backtesting `["AAPL", "MSFT"]` over 2020–2022 is clean, but any universe selection that filters on "currently exists" introduces survivorship bias. There's no mechanism to load delisted-security data or enforce point-in-time universe construction.

---

### 10. No benchmark / buy-and-hold comparison

Results are reported in isolation. There's no built-in way to run a passive benchmark alongside a strategy and compute alpha, beta, or information ratio.

---

### 11. Warm-up dilution is silent

Already documented in `StrategyContainer`'s docstring, but there's no mechanism to defer adding a strategy until its warm-up is complete, nor any warning emitted during diluted bars.

---

## Summary Priority Table

| Priority | Gap | Impact |
|---|---|---|
| Critical | Execution at current close (look-ahead) | Overstated returns |
| Critical | Equity curve gaps (fill-only) | Broken drawdown / Sharpe |
| Critical | Zero-fill contaminates indicators | Wrong signals |
| Important | No performance metrics | Can't evaluate strategies |
| Important | No position / leverage limits | Unrealistic sizing |
| Important | Integer truncation | Systematic under-allocation |
| Important | Flat commission only | Unrealistic costs |
| Moderate | No walk-forward / OOS framework | Overfitting risk |
| Moderate | Survivorship bias | Inflated universe performance |
| Moderate | No benchmark comparison | No alpha measurement |
| Moderate | Silent warm-up dilution | Unexpected signal dampening |

---

## Recommended Fix Order

1. **Next-open execution** — eliminates look-ahead bias, the most damaging issue
2. **Per-bar equity snapshots** — unlocks all time-series performance metrics
3. **Missing-bar handling** — prevents silent indicator corruption
4. **Performance metrics module** — `PerformanceAnalyzer` consuming the corrected equity curve
