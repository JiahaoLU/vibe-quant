"""
Entry point — wire all components together and run the backtest.
Modify SYMBOLS, START, END, INITIAL_CAPITAL, FAST_WINDOW, SLOW_WINDOW,
COMMISSION, SLIPPAGE_PCT to experiment.
"""
import queue

from analysis.result_writer import DefaultResultWriter
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
RESULTS_DIR     = "results"
RESULTS_FORMAT  = "parquet"  # "parquet" or "csv"
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

writer = DefaultResultWriter(
    initial_capital = INITIAL_CAPITAL,
    symbol_bars     = data.symbol_bars,
    results_dir     = RESULTS_DIR,
    fmt             = RESULTS_FORMAT,
)

bt = Backtester(events, data, strategy, portfolio, execution, result_writer=writer)
bt.run()
