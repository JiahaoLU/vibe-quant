"""
Thin wrappers over alpaca-py SDK.
Pure functions, no state, no imports from trading/.
"""
import asyncio
import contextlib
import logging
from datetime import datetime
from typing import Literal

logger = logging.getLogger(__name__)

from alpaca.data import StockHistoricalDataClient
from alpaca.data.requests import StockBarsRequest
from alpaca.data.timeframe import TimeFrame, TimeFrameUnit
from alpaca.trading.client import TradingClient
from alpaca.trading.enums import OrderSide, TimeInForce
from alpaca.trading.requests import MarketOrderRequest
from alpaca.trading.stream import TradingStream


# Alpaca SDK may emit either spelling ("canceled" or "cancelled")
TERMINAL_ORDER_STATUSES: frozenset[str] = frozenset({
    "canceled", "cancelled", "rejected", "expired", "done_for_day"
})


def _timeframe(bar_freq: str) -> TimeFrame:
    if bar_freq == "1d":
        return TimeFrame.Day
    if bar_freq == "1m":
        return TimeFrame.Minute
    if bar_freq.endswith("h"):
        return TimeFrame(int(bar_freq[:-1]), TimeFrameUnit.Hour)
    if bar_freq.endswith("m"):
        return TimeFrame(int(bar_freq[:-1]), TimeFrameUnit.Minute)
    raise ValueError(f"Unsupported bar_freq: {bar_freq!r}")


def fetch_bars(
    symbols: list[str],
    bar_freq: str,
    start: datetime,
    end: datetime,
    api_key: str,
    secret: str,
) -> dict[str, dict]:
    """Fetch OHLCV bars for symbols. Returns {symbol: {open, high, low, close, volume, timestamp}}."""
    client = StockHistoricalDataClient(api_key, secret)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=_timeframe(bar_freq),
        start=start,
        end=end,
    )
    bar_set = client.get_stock_bars(request)
    result = {}
    for symbol in symbols:
        bars = bar_set[symbol]
        if not bars:
            continue
        bar = bars[-1]
        result[symbol] = {
            "timestamp": bar.timestamp,
            "open":      float(bar.open),
            "high":      float(bar.high),
            "low":       float(bar.low),
            "close":     float(bar.close),
            "volume":    float(bar.volume),
        }
    return result


def fetch_bars_history(
    symbols: list[str],
    bar_freq: str,
    start: datetime,
    end: datetime,
    api_key: str,
    secret: str,
) -> dict[str, list[dict]]:
    """Fetch all OHLCV bars for symbols in [start, end].

    Returns {symbol: [oldest, ..., newest]} sorted by timestamp.
    Symbols with no bars in the window are omitted.
    """
    client = StockHistoricalDataClient(api_key, secret)
    request = StockBarsRequest(
        symbol_or_symbols=symbols,
        timeframe=_timeframe(bar_freq),
        start=start,
        end=end,
    )
    bar_set = client.get_stock_bars(request)
    result = {}
    for symbol in symbols:
        bars = bar_set[symbol]
        if not bars:
            continue
        result[symbol] = sorted(
            [
                {
                    "timestamp": bar.timestamp,
                    "open": float(bar.open),
                    "high": float(bar.high),
                    "low": float(bar.low),
                    "close": float(bar.close),
                    "volume": float(bar.volume),
                }
                for bar in bars
            ],
            key=lambda bar: bar["timestamp"],
        )
    return result


def submit_order(
    symbol: str,
    direction: Literal["BUY", "SELL"],
    quantity: int,
    api_key: str,
    secret: str,
    paper: bool,
    client_order_id: str = "",
) -> str:
    """Submit a market order. Returns the broker order ID."""
    client = TradingClient(api_key, secret, paper=paper)
    side = OrderSide.BUY if direction == "BUY" else OrderSide.SELL
    req = MarketOrderRequest(
        symbol=symbol,
        qty=quantity,
        side=side,
        time_in_force=TimeInForce.DAY,
    )
    if client_order_id:
        req.client_order_id = client_order_id
    order = client.submit_order(req)
    return str(order.id)


def get_positions(api_key: str, secret: str, paper: bool) -> dict[str, int]:
    """Return current positions as {symbol: quantity}."""
    client = TradingClient(api_key, secret, paper=paper)
    positions = client.get_all_positions()
    return {p.symbol: int(float(p.qty)) for p in positions}


def get_account(api_key: str, secret: str, paper: bool) -> float:
    """Return available cash balance."""
    client = TradingClient(api_key, secret, paper=paper)
    account = client.get_account()
    return float(account.cash)


def get_order_status(
    order_id: str,
    api_key: str,
    secret: str,
    paper: bool,
) -> dict | None:
    """Return fill status dict or None on error.
    Keys: status, filled_qty, filled_avg_price, symbol, direction."""
    client = TradingClient(api_key, secret, paper=paper)
    try:
        order = client.get_order_by_id(order_id)
        return {
            "status":           str(order.status),
            "filled_qty":       int(float(order.filled_qty or 0)),
            "filled_avg_price": float(order.filled_avg_price or 0.0),
            "symbol":           order.symbol,
            "direction":        "BUY" if str(order.side) == "buy" else "SELL",
        }
    except Exception:
        return None


def cancel_all_open_orders(api_key: str, secret: str, paper: bool) -> None:
    """Cancel all open orders at the broker.

    Logs a warning and continues on failure — a cancel error does not corrupt
    data, it only means stale orders may still be live at the broker.
    """
    logger.info("Cancelling all open broker orders before reconciliation.")
    client = TradingClient(api_key, secret, paper=paper)
    try:
        client.cancel_orders()
    except Exception as exc:
        logger.warning(
            "cancel_orders failed (%s); proceeding with reconciliation. "
            "Stale orders may still be open at the broker.",
            exc,
        )


def cancel_order(order_id: str, api_key: str, secret: str, paper: bool) -> None:
    """Cancel a single open order by ID. Logs and continues on failure."""
    client = TradingClient(api_key, secret, paper=paper)
    try:
        client.cancel_order_by_id(order_id)
        logger.info("Cancelled order %s", order_id)
    except Exception as exc:
        logger.warning("cancel_order %s failed: %s", order_id, exc)


@contextlib.asynccontextmanager
async def open_fill_stream(api_key: str, secret: str, paper: bool):
    """Async context manager that yields asyncio.Queue[dict] of raw trade update dicts.
    The queue receives every fill/partial_fill event from Alpaca's trade update stream."""
    q: asyncio.Queue = asyncio.Queue()
    stream = TradingStream(api_key, secret, paper=paper)

    @stream.subscribe_trade_updates
    async def _handler(data):
        if hasattr(data, "event") and str(data.event) in ("fill", "partial_fill"):
            await q.put(data)

    task = asyncio.create_task(stream.run())
    try:
        yield q
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
