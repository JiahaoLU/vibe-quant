from typing import Callable

from ..base.portfolio import Portfolio
from ..events import BarBundleEvent, Event, FillEvent, OrderEvent, StrategyBundleEvent, TickEvent


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
        self._get_bars                = get_bars
        self._symbols                 = symbols
        self._cash                    = initial_capital
        self._initial_capital         = initial_capital
        self._holdings: dict[str, int] = {s: 0 for s in symbols}
        self._equity_curve: list[dict] = []
        self._pending_signals: StrategyBundleEvent | None = None
        self._current_attribution: dict[str, dict[str, float]] = {}
        self._strategy_realized_pnl: dict[str, float] = {}
        self._strategy_traded_value: dict[str, float] = {}
        self._strategy_qty: dict[str, dict[str, float]] = {}  # sid → symbol → attributed shares held

    def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None:
        pending = self._pending_signals
        self._pending_signals = None
        self._current_attribution = pending.per_strategy if pending is not None else {}

        emitted_any = False
        available_cash = self._cash
        for symbol, signal_event in (pending.combined.items() if pending is not None else []):
            # No shorts: clamp negative signals to zero
            weight = max(0.0, signal_event.signal)
            bar = bar_bundle.bars.get(symbol)
            if bar is None:
                continue
            price = bar.open
            if price <= 0:
                continue

            target_qty  = int(weight * self._initial_capital / price)
            current_qty = self._holdings.get(symbol, 0)
            delta       = target_qty - current_qty

            if delta > 0 and available_cash >= delta * price:
                available_cash -= delta * price
                self._emit(OrderEvent(
                    symbol           = symbol,
                    timestamp        = bar_bundle.timestamp,
                    order_type       = "MARKET",
                    direction        = "BUY",
                    quantity         = delta,
                    reference_price  = price,
                    bar_volume       = bar.volume,
                    bar_high         = bar.high,
                    bar_low          = bar.low,
                    bar_close        = bar.close,
                    bar_is_synthetic = bar.is_synthetic,
                ))
                emitted_any = True
            elif delta < 0:
                self._emit(OrderEvent(
                    symbol           = symbol,
                    timestamp        = bar_bundle.timestamp,
                    order_type       = "MARKET",
                    direction        = "SELL",
                    quantity         = abs(delta),
                    reference_price  = price,
                    bar_volume       = bar.volume,
                    bar_high         = bar.high,
                    bar_low          = bar.low,
                    bar_close        = bar.close,
                    bar_is_synthetic = bar.is_synthetic,
                ))
                emitted_any = True

        if not emitted_any:
            self._emit(OrderEvent(
                symbol          = "",
                timestamp       = bar_bundle.timestamp,
                order_type      = "MARKET",
                direction       = "HOLD",
                quantity        = 0,
                reference_price = 0.0,
            ))

    def on_signal(self, event: StrategyBundleEvent) -> None:
        self._pending_signals = event

    def on_fill(self, event: FillEvent) -> None:
        if event.direction != "HOLD":
            multiplier = 1 if event.direction == "BUY" else -1
            self._holdings[event.symbol] = self._holdings.get(event.symbol, 0) + multiplier * event.quantity
            self._cash -= multiplier * event.fill_price * event.quantity + event.commission

            # Apportion fill's cash impact and share count across strategies
            # commission is always a cost (positive); add it regardless of direction
            fill_cash_impact = multiplier * event.fill_price * event.quantity + event.commission
            trade_value = event.fill_price * event.quantity
            for strategy_id, symbol_weights in self._current_attribution.items():
                share = symbol_weights.get(event.symbol, 0.0)
                if share:
                    self._strategy_realized_pnl[strategy_id] = (
                        self._strategy_realized_pnl.get(strategy_id, 0.0) - share * fill_cash_impact
                    )
                    self._strategy_traded_value[strategy_id] = (
                        self._strategy_traded_value.get(strategy_id, 0.0) + share * trade_value
                    )
                    sym_qty = self._strategy_qty.setdefault(strategy_id, {})
                    sym_qty[event.symbol] = sym_qty.get(event.symbol, 0.0) + multiplier * share * event.quantity

        market_value = 0.0
        strategy_market_value: dict[str, float] = {}
        for symbol in self._symbols:
            bars = self._get_bars(symbol, 1)
            if bars:
                price = bars[-1].close
                qty   = self._holdings.get(symbol, 0)
                market_value += qty * price
                for sid, sym_qty in self._strategy_qty.items():
                    strategy_market_value[sid] = (
                        strategy_market_value.get(sid, 0.0)
                        + sym_qty.get(symbol, 0.0) * price
                    )

        self._equity_curve.append({
            "timestamp":      event.timestamp,
            "cash":           self._cash,
            "holdings":       dict(self._holdings),
            "market_value":   market_value,
            "equity":         self._cash + market_value,
            "strategy_pnl":   dict(self._strategy_realized_pnl),
            "strategy_equity": {
                sid: self._strategy_realized_pnl.get(sid, 0.0) + strategy_market_value.get(sid, 0.0)
                for sid in self._strategy_realized_pnl
            },
        })

    @property
    def equity_curve(self) -> list[dict]:
        return self._equity_curve

    @property
    def strategy_pnl(self) -> list[dict]:
        return [
            {"timestamp": row["timestamp"], **row["strategy_pnl"]}
            for row in self._equity_curve
        ]

    @property
    def strategy_traded_value(self) -> dict[str, float]:
        return self._strategy_traded_value
