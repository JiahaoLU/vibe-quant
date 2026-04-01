# Volume-Based Slippage Model

## Problem with the current model

```python
fill_price = reference_price * (1 + direction_factor * slippage_pct)
```

Fixed-percentage slippage charges every trade the same fraction regardless of size or
liquidity. This is systematically wrong in both directions: it over-penalizes small
trades and under-penalizes large ones.

## Recommended upgrade: volume-scaled square-root market impact

Real slippage scales with **participation rate** — the fraction of the day's volume your
order represents. The square-root market impact model (Almgren et al.) is the industry
standard:

```
participation_rate = order_quantity / bar.volume
market_impact_pct  = η × σ × √(participation_rate)
```

Where `η` is a constant (~0.1–0.3 for liquid US equities) and `σ` is intraday
volatility. Both inputs are already available on `TickEvent` (`volume`, `high`, `low`,
`close`):

```python
import math

# Parkinson intraday volatility estimator
intraday_vol = (bar.high - bar.low) / bar.close / (2 * (2 * math.log(2)) ** 0.5)

participation = event.quantity / bar.volume if bar.volume > 0 else 0.0
impact_pct = eta * intraday_vol * participation ** 0.5

fill_price = reference_price * (1 + direction_factor * (self._slippage_pct + impact_pct))
```

A trade that is 1% of daily volume pays 10× less impact than one that is 100%.

## Spread-based floor (bid-ask cost)

Even with zero market impact, you always cross the spread. For daily OHLCV data, a
practical proxy uses Roll's model:

```
estimated_spread_pct = spread_fraction × (high - low) / close
```

Where `spread_fraction ≈ 0.3` (empirical constant). This gives a **minimum slippage
floor** even for tiny orders.

## Improvement tiers

| Tier | Change | Benefit | Complexity |
|---|---|---|---|
| **1** | Volume-scaled square-root impact | Correctly penalizes large orders | Low — volume already in `TickEvent` |
| **2** | Spread floor from high-low range | Realistic minimum cost | Low — high/low already in `TickEvent` |
| **3** | Separate `slippage_pct` per symbol | Liquid vs. illiquid names | Medium — needs per-symbol config |
| **4** | Guard synthetic bars (`is_synthetic=True`) → zero impact | No phantom costs on filled-forward bars | Low — flag already on `TickEvent` |

Tier 4 is a **bug fix**: the current code applies slippage on synthetic bars where
`volume=0`, which causes division-by-zero in the volume model. Short-circuit
`execute_order` when `bar.is_synthetic`.

## What not to do

- **Don't use close price as fill price** — orders fill at next open at best. The
  current model already does this right via `reference_price = bar.open`.
- **Don't calibrate slippage to match a known result** — that is overfitting the cost
  model.
- **Don't ignore volume entirely** — a strategy that trades 50% of daily volume looks
  profitable in backtests but is physically impossible to execute.

## Suggested constructor after upgrade

```python
SimulatedExecutionHandler(
    emit,
    commission_pct:    float = 0.001,  # 0.1% of trade value
    slippage_pct:      float = 0.0005, # fixed spread component
    market_impact_eta: float = 0.1,    # square-root impact coefficient
)
```

Total cost per fill = **spread + market impact**, both scaling with trade size and
liquidity.
