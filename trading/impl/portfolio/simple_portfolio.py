from datetime import datetime
from typing import Callable

from trading.base.live.risk_guard import RiskGuard

from ...base.portfolio import Portfolio
from ...events import BarBundleEvent, Event, FillEvent, OrderEvent, StrategyBundleEvent, TickEvent


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
        max_leverage:    float = 1.0,
        fill_cost_buffer: float = 0.002,
        risk_guard: RiskGuard | None = None,
    ):
        super().__init__(emit)
        self._get_bars                = get_bars
        self._symbols                 = symbols
        self._cash                    = initial_capital
        self._initial_capital         = initial_capital
        self._max_leverage            = max_leverage
        self._fill_cost_buffer        = fill_cost_buffer
        self._risk_guard              = risk_guard
        self._holdings: dict[str, int] = {s: 0 for s in symbols}
        self._equity_curve: list[dict] = []
        self._pending_signals: StrategyBundleEvent | None = None
        self._current_attribution: dict[str, dict[str, float]] = {}
        self._strategy_realized_pnl: dict[str, float] = {}
        self._strategy_traded_value: dict[str, float] = {}
        self._strategy_qty: dict[str, dict[str, float]] = {}  # sid → symbol → attributed shares held

    def _holdings_market_value(self) -> float:
        return sum(
            self._holdings.get(s, 0) * bars[-1].close
            for s in self._symbols
            if (bars := self._get_bars(s, 1))
        )

    def fill_pending_orders(self, bar_bundle: BarBundleEvent) -> None:
        pending = self._pending_signals
        self._pending_signals = None
        emitted_any = False

        for symbol, bar in bar_bundle.bars.items():
            if bar.is_delisted and self._holdings.get(symbol, 0) != 0:
                self._emit_order(symbol, bar_bundle.timestamp, "SELL", abs(self._holdings[symbol]), bar)
                emitted_any = True

        if not pending:
            self._current_attribution = {}
            if not emitted_any:
                self._emit_order("", bar_bundle.timestamp, "HOLD", 0)
            return

        self._current_attribution = pending.per_strategy

        # Compute equity and derive holdings value for leverage check
        current_equity = self.equity
        holdings_value = current_equity - self._cash
        max_gross_exposure = current_equity * self._max_leverage

        available_cash = self._cash
        for symbol, signal_event in pending.combined.items():
            bar = bar_bundle.bars.get(symbol)
            if bar is None or bar.is_delisted:
                continue
            # No shorts: clamp negative signals to zero
            weight = max(0.0, signal_event.signal)
            price = bar.open
            if price <= 0:
                continue

            target_qty = int(weight * self._initial_capital / price)
            delta      = target_qty - self._holdings.get(symbol, 0)

            if delta > 0:
                # Constraint 1: cash must cover order value + cost buffer (slippage + commission)
                max_qty_by_cash = int(available_cash / (price * (1.0 + self._fill_cost_buffer)))
                # Constraint 2: total gross exposure must not exceed equity × max_leverage
                # current_exposure includes existing holdings + orders already placed this bar
                current_exposure = holdings_value + (self._cash - available_cash)
                max_qty_by_leverage = max(0, int((max_gross_exposure - current_exposure) / price))
                affordable_qty = min(delta, max_qty_by_cash, max_qty_by_leverage)
                if affordable_qty > 0:
                    available_cash -= affordable_qty * price * (1.0 + self._fill_cost_buffer)
                    self._emit_order(symbol, bar_bundle.timestamp, "BUY", affordable_qty, bar)
                    emitted_any = True
            elif delta < 0:
                self._emit_order(symbol, bar_bundle.timestamp, "SELL", abs(delta), bar)
                emitted_any = True

        if not emitted_any:
            self._emit_order("", bar_bundle.timestamp, "HOLD", 0)

    def _emit_order(
        self,
        symbol: str,
        timestamp: datetime,
        direction: str,
        qty: int,
        bar: TickEvent | None = None,
    ) -> None:
        order = OrderEvent(
            symbol=symbol,
            timestamp=timestamp,
            order_type="MARKET",
            direction=direction,
            quantity=qty,
        )
        if bar:
            order.reference_price  = bar.open
            order.bar_volume       = bar.volume
            order.bar_high         = bar.high
            order.bar_low          = bar.low
            order.bar_close        = bar.close
            order.bar_is_synthetic = bar.is_synthetic
        self._emit(order)

    def on_signal(self, event: StrategyBundleEvent) -> None:
        if self._risk_guard is not None:
            current_prices = {
                s: bars[-1].close
                for s in self._symbols
                if (bars := self._get_bars(s, 1))
            }
            current_equity = self.equity
            event = self._risk_guard.check(event, current_prices, current_equity)
            if event is None:
                return
        self._pending_signals = event

    def on_fill(self, event: FillEvent) -> None:
        if event.direction != "HOLD":
            multiplier = 1 if event.direction == "BUY" else -1
            fill_cash_impact = multiplier * event.fill_price * event.quantity + event.commission
            self._holdings[event.symbol] = self._holdings.get(event.symbol, 0) + multiplier * event.quantity
            self._cash -= fill_cash_impact

            # Apportion fill's cash impact and share count across strategies
            # commission is always a cost (positive); add it regardless of direction
            trade_value = event.fill_price * event.quantity
            for strategy_id, symbol_weights in self._current_attribution.items():
                share = symbol_weights.get(event.symbol, 0.0)
                if not share:
                    continue
                
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
            if not bars:
                continue

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

    def restore(self, holdings: dict[str, int], cash: float) -> None:
        self._holdings = dict(holdings)
        self._cash = cash

    @property
    def equity(self) -> float:
        return self._cash + self._holdings_market_value()

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
