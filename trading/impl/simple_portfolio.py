from typing import Callable

from ..base.portfolio import Portfolio
from ..events import Event, FillEvent, OrderEvent, SignalBundleEvent, TickEvent


class SimplePortfolio(Portfolio):
    """
    Target-weight portfolio.  Each signal weight is relative to initial_capital:
      target_quantity = int(weight * initial_capital / price)

    Short positions are prohibited — any negative signal weight is clamped to 0.
    When multiple strategies send signals for the same symbol (via StrategyContainer),
    their weights are already combined before reaching this class; the portfolio just
    executes the delta between target and current holdings.
    """

    def __init__(
        self,
        emit:            Callable[[Event], None],
        get_bars:        Callable[[str, int], list[TickEvent]],
        symbols:         list[str],
        initial_capital: float = 10_000.0,
    ):
        super().__init__(emit)
        self._get_bars        = get_bars
        self._symbols         = symbols
        self._cash            = initial_capital
        self._initial_capital = initial_capital
        self._holdings: dict[str, int] = {s: 0 for s in symbols}
        self._equity_curve: list[dict] = []

    def on_signal(self, event: SignalBundleEvent) -> None:
        available_cash = self._cash
        for symbol, signal_event in event.signals.items():
            # No shorts: clamp negative signals to zero
            weight = max(0.0, signal_event.signal)

            bars = self._get_bars(symbol, 1)
            if not bars:
                continue
            price = bars[-1].close
            if price <= 0:
                continue

            target_qty  = int(weight * self._initial_capital / price)
            current_qty = self._holdings.get(symbol, 0)
            delta       = target_qty - current_qty

            if delta > 0:
                cost = delta * price
                if available_cash >= cost:
                    available_cash -= cost
                    self._emit(OrderEvent(
                        symbol          = symbol,
                        timestamp       = event.timestamp,
                        order_type      = "MARKET",
                        direction       = "BUY",
                        quantity        = delta,
                        reference_price = price,
                    ))
            elif delta < 0:
                self._emit(OrderEvent(
                    symbol          = symbol,
                    timestamp       = event.timestamp,
                    order_type      = "MARKET",
                    direction       = "SELL",
                    quantity        = abs(delta),
                    reference_price = price,
                ))

    def on_fill(self, event: FillEvent) -> None:
        multiplier = 1 if event.direction == "BUY" else -1
        self._holdings[event.symbol] = self._holdings.get(event.symbol, 0) + multiplier * event.quantity
        self._cash -= multiplier * event.fill_price * event.quantity + event.commission

        market_value = 0.0
        for symbol in self._symbols:
            bars = self._get_bars(symbol, 1)
            if bars:
                market_value += self._holdings.get(symbol, 0) * bars[-1].close

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
