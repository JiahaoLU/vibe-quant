import queue

from ..base.data import DataHandler
from ..base.portfolio import Portfolio
from ..events import FillEvent, OrderEvent, SignalBundleEvent


class SimplePortfolio(Portfolio):
    """
    Sizes every entry as 100% of available cash per symbol (first LONG wins if multiple arrive).
    Tracks cash, per-symbol holdings, and records equity snapshots on every fill.
    """

    def __init__(
        self,
        events:          queue.Queue,
        data:            DataHandler,
        symbols:         list[str],
        initial_capital: float = 10_000.0,
    ):
        self._events          = events
        self._data            = data
        self._symbols         = symbols
        self._cash            = initial_capital
        self._initial_capital = initial_capital
        self._holdings: dict[str, int] = {s: 0 for s in symbols}
        self._equity_curve: list[dict] = []

    def on_signal(self, event: SignalBundleEvent) -> None:
        available_cash = self._cash
        for symbol, signal in event.signals.items():
            bars = self._data.get_latest_bars(symbol, 1)
            if not bars:
                continue
            price = bars[-1]["close"]

            if signal.signal_type == "LONG" and self._holdings[symbol] == 0:
                quantity = int(available_cash // price)
                if quantity > 0:
                    available_cash -= quantity * price
                    self._events.put(OrderEvent(
                        symbol          = symbol,
                        timestamp       = event.timestamp,
                        order_type      = "MARKET",
                        direction       = "BUY",
                        quantity        = quantity,
                        reference_price = price,
                    ))

            elif signal.signal_type == "EXIT" and self._holdings[symbol] > 0:
                self._events.put(OrderEvent(
                    symbol          = symbol,
                    timestamp       = event.timestamp,
                    order_type      = "MARKET",
                    direction       = "SELL",
                    quantity        = self._holdings[symbol],
                    reference_price = price,
                ))

    def on_fill(self, event: FillEvent) -> None:
        multiplier = 1 if event.direction == "BUY" else -1
        self._holdings[event.symbol] += multiplier * event.quantity
        self._cash -= multiplier * event.fill_price * event.quantity + event.commission

        market_value = 0.0
        for symbol in self._symbols:
            bars = self._data.get_latest_bars(symbol, 1)
            if bars:
                market_value += self._holdings[symbol] * bars[-1]["close"]

        self._equity_curve.append({
            "timestamp":    event.timestamp,
            "cash":         self._cash,
            "holdings":     dict(self._holdings),
            "market_value": market_value,
            "equity":       self._cash + market_value,
        })

    @property
    def equity_curve(self) -> list[dict]:
        return self._equity_curve
