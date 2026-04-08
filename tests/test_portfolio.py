from datetime import datetime

from trading.impl.simple_portfolio import SimplePortfolio
from trading.events import (
    BarBundleEvent, FillEvent, OrderEvent, StrategyBundleEvent, SignalEvent, TickEvent,
)


def _get_bars(prices: dict[str, float]):
    def get_bars(symbol, n=1):
        p = prices[symbol]
        return [TickEvent(symbol=symbol, timestamp=datetime(2020, 1, 2), open=p, high=p, low=p, close=p, volume=1000.0)]
    return get_bars


def _strategy_bundle(symbol: str, signal: float, ts=None, strategy_id: str = "test") -> StrategyBundleEvent:
    ts = ts or datetime(2020, 1, 2)
    sig = SignalEvent(symbol=symbol, timestamp=ts, signal=signal)
    return StrategyBundleEvent(
        timestamp=ts,
        combined={symbol: sig},
        # per_strategy always populated — even on exit — so on_fill can attribute the SELL fill
        per_strategy={strategy_id: {symbol: 1.0}},
    )


def _fill(symbol: str, direction: str, quantity: int, price: float) -> FillEvent:
    return FillEvent(
        symbol=symbol, timestamp=datetime(2020, 1, 2),
        direction=direction, quantity=quantity,
        fill_price=price, commission=1.0,
    )


def _fill_bar(symbol: str, open_price: float, ts=None):
    ts = ts or datetime(2020, 1, 3)
    tick = TickEvent(symbol=symbol, timestamp=ts,
                     open=open_price, high=open_price, low=open_price, close=open_price, volume=1000.0)
    return BarBundleEvent(timestamp=ts, bars={symbol: tick})


def _delisted_bar(symbol: str, open_price: float, ts=None):
    ts = ts or datetime(2020, 1, 3)
    tick = TickEvent(
        symbol=symbol,
        timestamp=ts,
        open=open_price,
        high=open_price,
        low=open_price,
        close=open_price,
        volume=1000.0,
        is_delisted=True,
    )
    return BarBundleEvent(timestamp=ts, bars={symbol: tick})


def test_portfolio_constructor_accepts_emit_callable():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    assert portfolio is not None


def test_long_signal_emits_buy_order():
    collected = []
    portfolio = SimplePortfolio(
        collected.append,
        _get_bars({"AAPL": 100.0}),
        ["AAPL"],
        initial_capital=10_000.0,
        fill_cost_buffer=0.0,
    )

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    order = collected[0]
    assert isinstance(order, OrderEvent)
    assert order.symbol == "AAPL"
    assert order.direction == "BUY"
    assert order.quantity == 100   # int(1.0 * 10_000 / 100)
    assert order.reference_price == 100.0


def test_long_signal_topup_when_partial_holdings():
    """A signal with weight 1.0 tops up to the full target even when already holding."""
    from trading.events import FillEvent as _FE
    collected = []
    portfolio = SimplePortfolio(
        collected.append,
        _get_bars({"AAPL": 100.0}),
        ["AAPL"],
        initial_capital=10_000.0,
        fill_cost_buffer=0.0,
    )
    # Use commission=0 so cash arithmetic is exact: cash after buy = 10000 − 50*100 = 5000
    portfolio.on_fill(_FE(symbol="AAPL", timestamp=datetime(2020, 1, 2),
                          direction="BUY", quantity=50, fill_price=100.0, commission=0.0))
    collected.clear()

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    # target = int(1.0 * 10_000 / 100) = 100; held = 50; delta = 50; cost = 5000 ≤ cash 5000
    assert len(collected) == 1
    assert collected[0].direction == "BUY"
    assert collected[0].quantity == 50   # target 100 − held 50


def test_exit_signal_emits_sell_order():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_strategy_bundle("AAPL", 0.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "SELL"
    assert collected[0].quantity == 50


def test_exit_signal_no_order_when_no_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 0.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_short_signal_treated_as_exit():
    """Negative signal (short) is clamped to 0 — no short positions allowed."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    collected.clear()

    portfolio.on_signal(_strategy_bundle("AAPL", -0.5))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "SELL"
    assert collected[0].quantity == 50   # closes position, does not go short


def test_short_signal_no_order_when_flat():
    """Negative signal with no holdings → still no real order (clamped to 0); HOLD emitted for equity tracking."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", -1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_on_fill_updates_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 50


def test_on_fill_sell_decreases_holdings():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 50, 100.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 50, 100.0))
    assert portfolio.equity_curve[-1]["holdings"]["AAPL"] == 0


def test_equity_sums_all_symbol_holdings():
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 200.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))
    snapshot = portfolio.equity_curve[-1]
    assert snapshot["market_value"] == 1000.0
    assert snapshot["holdings"] == {"AAPL": 10, "MSFT": 0}


def test_long_signal_no_order_when_no_cash():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=50.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    # target = int(1.0 * 50 / 100) = 0 → delta = 0 → no real order → HOLD
    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_multi_symbol_normalised_signals_do_not_overdraw_cash():
    """Equal-weight signals (0.5 each) for 2 symbols should fit within initial_capital."""
    collected = []
    prices = {"AAPL": 100.0, "MSFT": 100.0}
    portfolio = SimplePortfolio(collected.append, _get_bars(prices), ["AAPL", "MSFT"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={
            "AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=0.5),
            "MSFT": SignalEvent(symbol="MSFT", timestamp=ts, signal=0.5),
        },
        per_strategy={
            "test": {"AAPL": 1.0, "MSFT": 1.0},
        },
    )
    portfolio.on_signal(bundle)

    fill_ts = datetime(2020, 1, 3)
    fill_bar = BarBundleEvent(
        timestamp=fill_ts,
        bars={
            "AAPL": TickEvent(symbol="AAPL", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
            "MSFT": TickEvent(symbol="MSFT", timestamp=fill_ts, open=100.0, high=100.0, low=100.0, close=100.0, volume=1000.0),
        },
    )
    portfolio.fill_pending_orders(fill_bar)

    total_order_value = sum(o.quantity * o.reference_price for o in collected)
    assert total_order_value <= 10_000.0, f"Orders exceed cash: {total_order_value}"


def test_fill_pending_orders_uses_open_price():
    """fill_pending_orders uses the fill bar's open price, not the signal bar's close."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))  # signal at close=100

    fill_ts = datetime(2020, 1, 3)
    fill_bar = BarBundleEvent(
        timestamp=fill_ts,
        bars={"AAPL": TickEvent(symbol="AAPL", timestamp=fill_ts,
                                open=105.0, high=106.0, low=104.0, close=105.5, volume=1000.0)},
    )
    portfolio.fill_pending_orders(fill_bar)

    assert len(collected) == 1
    assert collected[0].reference_price == 105.0   # open of fill bar, not 100.0


def test_fill_pending_orders_no_op_before_any_signal():
    """fill_pending_orders with no pending emits a HOLD order for equity tracking."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_pending_signals_cleared_after_fill():
    """A second fill_pending_orders call after the first emits a HOLD (pending was cleared)."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))  # emits BUY
    collected.clear()

    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))  # pending cleared → HOLD

    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_on_signal_does_not_emit_orders_directly():
    """on_signal stores pending only — calling it without fill_pending_orders emits nothing."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))

    assert collected == []


def test_hold_order_records_equity_without_changing_holdings():
    """HOLD fill records an equity snapshot but leaves cash and holdings unchanged."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_fill(FillEvent(
        symbol="", timestamp=datetime(2020, 1, 2),
        direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
    ))

    assert len(portfolio.equity_curve) == 1
    snap = portfolio.equity_curve[-1]
    assert snap["cash"] == 10_000.0           # unchanged
    assert snap["holdings"] == {"AAPL": 0}    # "" sentinel not present
    assert snap["equity"] == 10_000.0


def test_fill_pending_orders_emits_hold_when_no_real_orders():
    """fill_pending_orders with no pending emits exactly one HOLD order."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))

    assert len(collected) == 1
    assert collected[0].direction == "HOLD"
    assert collected[0].quantity == 0


def test_single_strategy_realized_pnl_equals_total_cash_impact():
    """With one strategy, realized_pnl tracks all fills at 100% attribution."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    # BUY 10 @ 100, commission 1.0 → cash impact = 10*100 + 1 = 1001 (cost)
    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 100, 100.0))   # 100 shares @ 100, comm 1.0

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]
    assert "s1" in pnl
    assert abs(pnl["s1"] - (-100 * 100.0 - 1.0)) < 1e-6   # -(cost + commission)


def test_single_strategy_buy_then_sell_profit():
    """Buy at 100, sell at 120 → realized PnL = 120*qty - 100*qty - 2*commission."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))    # cost: 10*100 + 1 = 1001

    portfolio.on_signal(_strategy_bundle("AAPL", 0.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 120.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 10, 120.0))   # revenue: 10*120 - 1 = 1199

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]
    assert abs(pnl - (10 * 120.0 - 1.0 - 10 * 100.0 - 1.0)) < 1e-6   # 198.0


def test_two_strategies_equal_nominal_split_commission():
    """Two equal-nominal strategies each absorb 50% of the commission."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    ts = datetime(2020, 1, 2)
    bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)},
        per_strategy={"a": {"AAPL": 0.5}, "b": {"AAPL": 0.5}},
    )
    portfolio.on_signal(bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))   # commission = 1.0

    pnl = portfolio.equity_curve[-1]["strategy_pnl"]
    # Each strategy absorbs 50% of cost: -(10*100 + 1) * 0.5 = -500.5
    assert abs(pnl["a"] - (-500.5)) < 1e-6
    assert abs(pnl["b"] - (-500.5)) < 1e-6


def test_full_exit_fill_pnl_not_zero():
    """After a full exit (combined==0), the SELL fill's PnL is still attributed (not silently dropped)."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    # Buy via a bundle where combined > 0
    ts = datetime(2020, 1, 2)
    buy_bundle = StrategyBundleEvent(
        timestamp=ts,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts, signal=1.0)},
        per_strategy={"s1": {"AAPL": 1.0}},
    )
    portfolio.on_signal(buy_bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))

    pnl_after_buy = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]

    # Sell via a bundle where combined == 0 — per_strategy has s1 with full exit attribution
    sell_bundle = StrategyBundleEvent(
        timestamp=datetime(2020, 1, 3),
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=datetime(2020, 1, 3), signal=0.0)},
        per_strategy={"s1": {"AAPL": 1.0}},   # full-exit attribution from container
    )
    portfolio.on_signal(sell_bundle)
    portfolio.fill_pending_orders(_fill_bar("AAPL", 120.0))
    portfolio.on_fill(_fill("AAPL", "SELL", 10, 120.0))

    pnl_after_sell = portfolio.equity_curve[-1]["strategy_pnl"]["s1"]
    # buy: -(10*100 + 1) = -1001; sell: -(-1*10*120 + 1) = +1199; net = 198.0
    assert abs(pnl_after_sell - 198.0) < 1e-6


def test_hold_fill_does_not_change_strategy_pnl():
    """HOLD fills do not affect strategy_pnl."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))
    pnl_before = dict(portfolio.equity_curve[-1]["strategy_pnl"])

    from trading.events import FillEvent
    portfolio.on_fill(FillEvent(
        symbol="", timestamp=datetime(2020, 1, 3),
        direction="HOLD", quantity=0, fill_price=0.0, commission=0.0,
    ))
    pnl_after = portfolio.equity_curve[-1]["strategy_pnl"]
    assert pnl_after == pnl_before


def test_strategy_pnl_property_matches_equity_curve():
    """strategy_pnl property returns rows with timestamp + strategy columns."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0, strategy_id="s1"))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    portfolio.on_fill(_fill("AAPL", "BUY", 10, 100.0))

    rows = portfolio.strategy_pnl
    assert len(rows) == 1
    assert "timestamp" in rows[0]
    assert "s1" in rows[0]


def test_fill_pending_orders_populates_bar_fields_on_buy():
    """BUY OrderEvent carries bar's volume/high/low/close/is_synthetic."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    ts_signal = datetime(2020, 1, 2)
    portfolio.on_signal(StrategyBundleEvent(
        timestamp=ts_signal,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts_signal, signal=1.0)},
        per_strategy={"s": {"AAPL": 1.0}},
    ))

    ts_fill = datetime(2020, 1, 3)
    bar = TickEvent(symbol="AAPL", timestamp=ts_fill,
                    open=102.0, high=105.0, low=98.0, close=103.0,
                    volume=12_000.0, is_synthetic=False)
    portfolio.fill_pending_orders(BarBundleEvent(timestamp=ts_fill, bars={"AAPL": bar}))

    order = collected[0]
    assert order.direction == "BUY"
    assert order.bar_volume == 12_000.0
    assert order.bar_high == 105.0
    assert order.bar_low == 98.0
    assert order.bar_close == 103.0
    assert order.bar_is_synthetic is False


def test_fill_pending_orders_populates_bar_fields_on_sell():
    """SELL OrderEvent carries bar's volume/high/low/close/is_synthetic."""
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)
    portfolio.on_fill(FillEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 1),
        direction="BUY", quantity=50, fill_price=100.0, commission=0.0,
    ))

    ts_signal = datetime(2020, 1, 2)
    portfolio.on_signal(StrategyBundleEvent(
        timestamp=ts_signal,
        combined={"AAPL": SignalEvent(symbol="AAPL", timestamp=ts_signal, signal=0.0)},
        per_strategy={"s": {"AAPL": 1.0}},
    ))

    ts_fill = datetime(2020, 1, 3)
    bar = TickEvent(symbol="AAPL", timestamp=ts_fill,
                    open=110.0, high=112.0, low=108.0, close=111.0,
                    volume=8_000.0, is_synthetic=True)
    portfolio.fill_pending_orders(BarBundleEvent(timestamp=ts_fill, bars={"AAPL": bar}))

    order = collected[0]
    assert order.direction == "SELL"
    assert order.bar_volume == 8_000.0
    assert order.bar_high == 112.0
    assert order.bar_low == 108.0
    assert order.bar_close == 111.0
    assert order.bar_is_synthetic is True


def test_delisted_bar_force_closes_open_position():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_fill_bar("AAPL", 100.0))
    collected.clear()
    portfolio.on_fill(_fill("AAPL", "BUY", 100, 100.0))

    portfolio.fill_pending_orders(_delisted_bar("AAPL", 95.0))

    orders = [order for order in collected if isinstance(order, OrderEvent) and order.direction == "SELL"]
    assert len(orders) == 1
    assert orders[0].symbol == "AAPL"
    assert orders[0].quantity == 100


def test_delisted_bar_with_no_position_emits_no_sell():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.fill_pending_orders(_delisted_bar("AAPL", 95.0))

    sell_orders = [order for order in collected if isinstance(order, OrderEvent) and order.direction == "SELL"]
    assert len(sell_orders) == 0


def test_signal_for_delisted_symbol_is_ignored():
    collected = []
    portfolio = SimplePortfolio(collected.append, _get_bars({"AAPL": 100.0}), ["AAPL"], initial_capital=10_000.0)

    portfolio.on_signal(_strategy_bundle("AAPL", 1.0))
    portfolio.fill_pending_orders(_delisted_bar("AAPL", 100.0))

    buy_orders = [order for order in collected if isinstance(order, OrderEvent) and order.direction == "BUY"]
    assert len(buy_orders) == 0
