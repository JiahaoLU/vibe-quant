"""
Live / paper trading entry point.
Set MODE = "paper" to route orders to Alpaca's paper API (default).
Set MODE = "live"  to route orders to Alpaca's live API (real capital).

Credentials are loaded from environment variables:
  ALPACA_API_KEY, ALPACA_SECRET_KEY
  (For live mode the same vars are used; Alpaca distinguishes paper vs live
  via the paper= flag, not separate credentials.)

Strategy params are loaded from strategy_params/ exactly as in run_backtest.py.
"""
import asyncio
import os
import queue

from trading.impl import (
    AlpacaDataHandler,
    AlpacaExecutionHandler,
    AlpacaPaperExecutionHandler,
    AlpacaReconciler,
    JsonStrategyParamsLoader,
    LiveRunner,
    RiskGuard,
    SimplePortfolio,
    StrategyContainer,
)

# --- Configuration -----------------------------------------------------------
MODE               = "paper"            # "paper" | "live"
STRATEGY_PARAMS_DIR = "strategy_params"
INITIAL_CAPITAL    = 10_000.0
MAX_LEVERAGE       = 1.0
FILL_COST_BUFFER   = 0.002
MAX_DAILY_LOSS_PCT = 0.05               # halt if equity drops 5% from day open
MAX_POSITION_PCT   = 0.20              # cap any single position at 20% of equity
# -----------------------------------------------------------------------------

API_KEY = os.environ["ALPACA_API_KEY"]
SECRET  = os.environ["ALPACA_SECRET_KEY"]

events   = queue.Queue()
data     = None   # resolved after strategy symbols are known

loader   = JsonStrategyParamsLoader(STRATEGY_PARAMS_DIR)
strategy = StrategyContainer(events.put, lambda s, n: data.get_latest_bars(s, n))
for strategy_cls, params in loader.load_all():
    strategy.add(strategy_cls, params)

symbols = strategy.symbols

data = AlpacaDataHandler(
    emit     = events.put,
    symbols  = symbols,
    bar_freq = strategy.required_freq,
    api_key  = API_KEY,
    secret   = SECRET,
)

execution = (
    AlpacaPaperExecutionHandler(events.put, api_key=API_KEY, secret=SECRET)
    if MODE == "paper"
    else AlpacaExecutionHandler(events.put, api_key=API_KEY, secret=SECRET)
)

risk_guard = RiskGuard(
    max_daily_loss_pct = MAX_DAILY_LOSS_PCT,
    max_position_pct   = MAX_POSITION_PCT,
    initial_capital    = INITIAL_CAPITAL,
)

reconciler = AlpacaReconciler(api_key=API_KEY, secret=SECRET, paper=(MODE == "paper"))

portfolio = SimplePortfolio(
    emit             = events.put,
    get_bars         = data.get_latest_bars,
    symbols          = symbols,
    initial_capital  = INITIAL_CAPITAL,
    max_leverage     = MAX_LEVERAGE,
    fill_cost_buffer = FILL_COST_BUFFER,
    risk_guard       = risk_guard,
)

runner = LiveRunner(events, data, strategy, portfolio, execution, reconciler, risk_guard)

if __name__ == "__main__":
    asyncio.run(runner.run())
