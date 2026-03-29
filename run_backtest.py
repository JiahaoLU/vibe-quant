"""
Entry point — wire all components together and run the backtest.
Modify SYMBOLS, START, END, INITIAL_CAPITAL, FAST_WINDOW, SLOW_WINDOW,
COMMISSION, SLIPPAGE_PCT to experiment.
"""
import csv
import queue

from external.yahoo import fetch_daily_bars
from trading.backtester import Backtester
from trading.impl import (
    SimulatedExecutionHandler,
    SimplePortfolio,
    SMACrossoverStrategy,
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
strategy.add(SMACrossoverStrategy, symbols=SYMBOLS, fast=FAST_WINDOW, slow=SLOW_WINDOW)

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
