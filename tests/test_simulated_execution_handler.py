import math
from datetime import datetime

from trading.events import FillEvent, OrderEvent
from trading.impl.execution_handler.simulated_execution_handler import SimulatedExecutionHandler


def _order(
    direction="BUY", quantity=100, reference_price=100.0,
    bar_volume=10_000.0, bar_high=105.0, bar_low=95.0, bar_close=100.0,
    bar_is_synthetic=False,
):
    return OrderEvent(
        symbol="AAPL", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction=direction, quantity=quantity,
        reference_price=reference_price,
        bar_volume=bar_volume, bar_high=bar_high, bar_low=bar_low,
        bar_close=bar_close, bar_is_synthetic=bar_is_synthetic,
    )


def _handler(commission_pct=0.0, slippage_pct=0.0, market_impact_eta=0.0):
    collected = []
    h = SimulatedExecutionHandler(
        collected.append,
        commission_pct=commission_pct,
        slippage_pct=slippage_pct,
        market_impact_eta=market_impact_eta,
    )
    return h, collected


# --- Constructor -------------------------------------------------------

def test_constructor_accepts_market_impact_eta():
    h, _ = _handler(market_impact_eta=0.1)
    assert h._market_impact_eta == 0.1


# --- Tier 4: Synthetic guard -------------------------------------------

def test_synthetic_bar_uses_only_fixed_slippage():
    """Synthetic bar: no impact, no spread floor — only fixed slippage_pct."""
    h, collected = _handler(slippage_pct=0.0005, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="BUY", quantity=100, reference_price=100.0,
        bar_volume=0.0, bar_high=105.0, bar_low=95.0, bar_close=100.0,
        bar_is_synthetic=True,
    ))
    fill = collected[0]
    assert isinstance(fill, FillEvent)
    # fill = 100 * (1 + 0.0005) = 100.05 — no impact applied
    assert abs(fill.fill_price - 100.05) < 1e-9


def test_synthetic_bar_no_division_by_zero():
    """volume=0 on synthetic bar must not raise ZeroDivisionError."""
    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        bar_volume=0.0, bar_is_synthetic=True,
    ))
    assert len(collected) == 1


def test_real_bar_zero_close_does_not_raise():
    """bar_close=0 on a non-synthetic bar must not raise ZeroDivisionError."""
    h, collected = _handler(slippage_pct=0.001, market_impact_eta=0.1)
    h.execute_order(_order(
        bar_close=0.0, bar_high=105.0, bar_low=95.0,
        bar_volume=10_000.0, bar_is_synthetic=False,
    ))
    assert len(collected) == 1


# --- Tier 2: Spread floor ----------------------------------------------

def test_spread_floor_dominates_fixed_slippage():
    """Wide H-L range → spread floor is larger than slippage_pct."""
    # bar: high=110, low=90, close=100 → spread_floor = 0.3 * 20/100 = 0.06
    # slippage_pct=0.0005 (much smaller); eta=0 so no impact
    h, collected = _handler(slippage_pct=0.0005, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=1, reference_price=100.0,
        bar_volume=10_000.0, bar_high=110.0, bar_low=90.0, bar_close=100.0,
        bar_is_synthetic=False,
    ))
    fill = collected[0]
    # base = max(0.0005, 0.06) = 0.06; impact = 0; fill = 100 * 1.06 = 106.0
    assert abs(fill.fill_price - 106.0) < 1e-9


def test_fixed_slippage_wins_when_range_is_narrow():
    """Narrow H-L range → fixed slippage_pct is larger than spread floor."""
    # bar: high=100.1, low=99.9, close=100 → spread_floor = 0.3 * 0.2/100 = 0.0006
    # slippage_pct=0.001 > 0.0006; eta=0
    h, collected = _handler(slippage_pct=0.001, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=1, reference_price=100.0,
        bar_volume=10_000.0, bar_high=100.1, bar_low=99.9, bar_close=100.0,
        bar_is_synthetic=False,
    ))
    fill = collected[0]
    # base = max(0.001, 0.0006) = 0.001; impact = 0; fill = 100 * 1.001 = 100.1
    assert abs(fill.fill_price - 100.1) < 1e-9


# --- Tier 1: Volume-scaled market impact -------------------------------

def test_large_order_gets_more_slippage_than_small():
    """Higher participation rate → higher market impact → worse fill price."""
    # bar: high=105, low=95, close=100, volume=10_000; eta=0.1; slippage_pct=0
    h_small, c_small = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h_large, c_large = _handler(slippage_pct=0.0, market_impact_eta=0.1)

    common = dict(reference_price=100.0,
                  bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
                  bar_close=100.0, bar_is_synthetic=False)

    h_small.execute_order(_order(direction="BUY", quantity=10, **common))
    h_large.execute_order(_order(direction="BUY", quantity=1_000, **common))

    fill_small = c_small[0].fill_price
    fill_large = c_large[0].fill_price
    assert fill_large > fill_small, (
        f"large order ({fill_large}) should be worse than small ({fill_small})"
    )


def test_market_impact_exact_value():
    """Verify the exact fill price for a known participation rate (eta=0.1)."""
    # bar: high=105, low=95, close=100, volume=10_000
    # sigma = (105-95)/100 / (2*sqrt(2*ln(2))) = 0.1 / 2.354820 ≈ 0.042474
    # participation = 100 / 10_000 = 0.01
    # impact = 0.1 * 0.042474 * sqrt(0.01) = 0.1 * 0.042474 * 0.1 = 0.00042474
    # spread_floor = 0.3 * 10/100 = 0.03
    # base = max(0.0, 0.03) = 0.03 (slippage_pct=0.0)
    # fill = 100 * (1 + 0.03 + 0.00042474) = 103.042474
    DENOM = 2 * (2 * math.log(2)) ** 0.5
    sigma = (105.0 - 95.0) / 100.0 / DENOM
    impact = 0.1 * sigma * (100.0 / 10_000.0) ** 0.5
    spread_floor = 0.3 * (105.0 - 95.0) / 100.0
    expected_fill = 100.0 * (1 + max(0.0, spread_floor) + impact)

    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="BUY", quantity=100, reference_price=100.0,
        bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    assert abs(collected[0].fill_price - expected_fill) < 1e-9


def test_sell_impact_reduces_fill_price():
    """SELL with market impact produces a fill_price below reference_price."""
    h, collected = _handler(slippage_pct=0.0, market_impact_eta=0.1)
    h.execute_order(_order(
        direction="SELL", quantity=500, reference_price=100.0,
        bar_volume=10_000.0, bar_high=105.0, bar_low=95.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    assert collected[0].fill_price < 100.0


# --- Commission --------------------------------------------------------

def test_commission_computed_on_fill_price_not_reference():
    """Commission is fraction of actual fill_price × quantity."""
    h, collected = _handler(commission_pct=0.001, slippage_pct=0.0, market_impact_eta=0.0)
    h.execute_order(_order(
        direction="BUY", quantity=10, reference_price=100.0,
        bar_volume=10_000.0, bar_high=100.0, bar_low=100.0,
        bar_close=100.0, bar_is_synthetic=False,
    ))
    fill = collected[0]
    # spread_floor = 0 (high==low); impact=0; fill_price = 100.0
    assert abs(fill.commission - 100.0 * 10 * 0.001) < 1e-9


# --- HOLD pass-through -------------------------------------------------

def test_hold_order_passes_through_unchanged():
    h, collected = _handler(slippage_pct=0.001, market_impact_eta=0.1)
    h.execute_order(OrderEvent(
        symbol="", timestamp=datetime(2020, 1, 2),
        order_type="MARKET", direction="HOLD", quantity=0,
    ))
    fill = collected[0]
    assert fill.direction == "HOLD"
    assert fill.fill_price == 0.0
    assert fill.commission == 0.0
