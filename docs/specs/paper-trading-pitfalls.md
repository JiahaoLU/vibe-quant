1. Smoke test before market hours

export ALPACA_API_KEY=...
export ALPACA_SECRET_KEY=...
python run_live.py

This will run reconciler.hydrate() and data.prefill() even before market open — you'll catch credential
issues, import errors, and DB setup immediately. Then Ctrl+C.

2. First live session — watch the pipeline end-to-end

Run during market hours and verify each stage fired:

sqlite3 logs/trades.db "SELECT * FROM signals ORDER BY ts DESC LIMIT 10;"
sqlite3 logs/trades.db "SELECT * FROM orders ORDER BY ts DESC LIMIT 10;"
sqlite3 logs/trades.db "SELECT * FROM fills ORDER BY ts DESC LIMIT 10;"

A healthy first session should show: signals → orders → fills in sequence. If signals fire but no orders
appear, the issue is in SimplePortfolio. If orders fire but no fills, check AlpacaPaperExecutionHandler.

3. Validate drift vs. backtest

After ~2 weeks, the critical check is:

- Live Sharpe ≥ 50% of backtest Sharpe — if below this, you have execution model mismatch
- Position sizes match expectations — target_qty = int(signal × initial_capital / price) should be
predictable
- No runaway orders — the RiskGuard daily loss limit (currently 5%) should be tested by checking equity
drawdown handling

4. Key risk parameters to review before extended paper run

In run_live.py:
- MAX_POSITION_PCT = 0.20 — 20% single position is high for a 10k account; consider 10-15%
- FILL_COST_BUFFER = 0.002 — 20bps is reasonable for equities; verify it matches your strategy's actual
spread
- MAX_LEVERAGE = 1.0 — correct for initial testing

What paper trading will NOT catch

- Borrow costs / short availability (your system currently prohibits shorts anyway)
- Slippage on larger size (10k is small enough that market impact is negligible)
- Partial fills — verify AlpacaPaperExecutionHandler handles partial fills if your strategy ever trades
illiquid names

The most common failure mode: strategy fires signals but SimplePortfolio computes target_qty = 0 because
initial_capital / price rounds down. Check this for any high-priced symbols.