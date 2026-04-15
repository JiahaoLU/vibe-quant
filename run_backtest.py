"""
Entry point — wire all components together and run the backtest.
Modify START, END, INITIAL_CAPITAL, COMMISSION_PCT, SLIPPAGE_PCT,
MARKET_IMPACT_ETA to experiment. Strategy-specific params live in
strategy_params/<strategy_name>.json and are registered in
strategy_params/params.json.
"""
import queue

from trading.logging_config import configure_logging
from analysis.result_writer import DefaultResultWriter
from external.index_constituents import load_or_fetch_universe_manifest
from external.yahoo import fetch_bars
from trading.backtester import Backtester
from trading.impl import (
    IndexConstituentsUniverseBuilder,
    JsonStrategyParamsLoader,
    SimulatedExecutionHandler,
    SimplePortfolio,
    StrategyContainer,
    YahooDataHandler,
)

# --- Configuration -----------------------------------------------------------
START               = "2025-01-01"
END                 = "2026-01-01"
STRATEGY_PARAMS_DIR = "strategy_params"
INITIAL_CAPITAL     = 10_000.0
COMMISSION_PCT      = 0.001  # 0.1% of trade value per fill
SLIPPAGE_PCT        = 0.0005 # fixed spread floor (one-way minimum cost)
MARKET_IMPACT_ETA   = 0.1    # square-root impact coefficient (Almgren et al.)
MAX_LEVERAGE        = 1.0    # max gross exposure as a multiple of current equity
FILL_COST_BUFFER    = 0.002  # cash reserve fraction for slippage + commission on buys
RESULTS_DIR         = "results"
RESULTS_FORMAT      = "parquet"  # "parquet" or "csv"
USE_UNIVERSE_GATING = True
INDEX_CODE          = "sp500"
RELOAD_UNIVERSE     = False
LOG_DIR             = "logs"
# -----------------------------------------------------------------------------

configure_logging(log_dir=LOG_DIR)

events   = queue.Queue()
data     = None  # resolved after strategy symbols are known

loader   = JsonStrategyParamsLoader(STRATEGY_PARAMS_DIR)
strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
for strategy_cls, params in loader.load_all():
    strategy.add(strategy_cls, params)

symbols = strategy.symbols
universe_builder = None
if USE_UNIVERSE_GATING:
    manifest_path = load_or_fetch_universe_manifest(
        INDEX_CODE,
        START,
        END,
        reload=RELOAD_UNIVERSE,
    )
    universe_builder = IndexConstituentsUniverseBuilder(manifest_path)

data = YahooDataHandler(
    events.put,
    symbols,
    start=START,
    end=END,
    fetch=fetch_bars,
    universe_builder=universe_builder,
    bar_freq=strategy.required_freq,
)
portfolio = SimplePortfolio(
    events.put, data.get_latest_bars, symbols,
    initial_capital  = INITIAL_CAPITAL,
    max_leverage     = MAX_LEVERAGE,
    fill_cost_buffer = FILL_COST_BUFFER,
)
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
