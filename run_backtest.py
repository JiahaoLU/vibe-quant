"""
Entry point — wire all components together and run the backtest.
Modify SYMBOLS, START, END, INITIAL_CAPITAL, FAST_WINDOW, SLOW_WINDOW,
COMMISSION, SLIPPAGE_PCT to experiment.
"""
import csv
import queue

from external.yahoo import fetch_daily_bars
from strategies.sma_crossover_strategy import SMACrossoverStrategy, SMACrossoverStrategyParams
from trading.backtester import Backtester
from trading.impl import (
    SimulatedExecutionHandler,
    SimplePortfolio,
    StrategyContainer,
    YahooDataHandler,
)

# --- Configuration -----------------------------------------------------------
SYMBOLS         = ["AAPL", "MSFT"]
START           = "2020-01-01"
END             = "2022-01-01"
INITIAL_CAPITAL = 10_000.0
FAST_WINDOW     = 10
SLOW_WINDOW     = 30
COMMISSION      = 1.0    # dollars per trade
SLIPPAGE_PCT    = 0.0005 # 0.05%
RESULTS_PATH    = "results/equity_curve.csv"
# -----------------------------------------------------------------------------

events   = queue.Queue()
data     = None  # resolved after strategy symbols are known

strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
strategy.add(SMACrossoverStrategy, SMACrossoverStrategyParams(
    symbols=SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW))

symbols   = strategy.symbols
data      = YahooDataHandler(events.put, symbols, start=START, end=END, fetch=fetch_daily_bars)
portfolio = SimplePortfolio(events.put, data.get_latest_bars, symbols, initial_capital=INITIAL_CAPITAL)
execution = SimulatedExecutionHandler(events.put, commission=COMMISSION, slippage_pct=SLIPPAGE_PCT)

bt = Backtester(events, data, strategy, portfolio, execution)
bt.run()

curve = portfolio.equity_curve
if not curve:
    print("No trades were executed — strategy never triggered.")
else:
    final_equity = curve[-1]["equity"]
    total_return = (final_equity / INITIAL_CAPITAL - 1) * 100

    print(f"Initial capital : ${INITIAL_CAPITAL:>10,.2f}")
    print(f"Final equity    : ${final_equity:>10,.2f}")
    print(f"Total return    : {total_return:>+.2f}%")
    print(f"Trades (fills)  : {len(curve)}")

    # Per-strategy realized PnL summary
    final_pnl = curve[-1]["strategy_pnl"]
    if final_pnl:
        print("\nStrategy realized PnL:")
        for strategy_id, pnl in sorted(final_pnl.items()):
            print(f"  {strategy_id:<30} ${pnl:>+10,.2f}")

    with open(RESULTS_PATH, "w", newline="") as f:
        fieldnames = ["timestamp", "cash", "holdings", "market_value", "equity"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in curve:
            writer.writerow({
                "timestamp":    row["timestamp"],
                "cash":         row["cash"],
                "holdings":     str(row["holdings"]),
                "market_value": row["market_value"],
                "equity":       row["equity"],
            })
    print(f"Equity curve    : {RESULTS_PATH}")

    # Export per-strategy PnL CSV
    strategy_pnl_rows = portfolio.strategy_pnl
    if strategy_pnl_rows:
        strategy_ids = [k for k in strategy_pnl_rows[-1] if k != "timestamp"]
        pnl_path = RESULTS_PATH.replace("equity_curve.csv", "strategy_pnl.csv")
        with open(pnl_path, "w", newline="") as f:
            fieldnames = ["timestamp"] + strategy_ids
            writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
            writer.writeheader()
            for row in strategy_pnl_rows:
                writer.writerow(row)
        print(f"Strategy PnL    : {pnl_path}")
