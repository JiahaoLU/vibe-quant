from zoneinfo import ZoneInfo


def test_market_hours_constants_exist_and_have_correct_types():
    from trading.market_hours import (
        MARKET_TZ,
        MARKET_CLOSE_HOUR,
        MARKET_CLOSE_MINUTE,
        DAILY_BAR_FETCH_HOUR,
        DAILY_BAR_FETCH_MINUTE,
    )
    assert isinstance(MARKET_TZ, ZoneInfo)
    assert isinstance(MARKET_CLOSE_HOUR, int)
    assert isinstance(MARKET_CLOSE_MINUTE, int)
    assert isinstance(DAILY_BAR_FETCH_HOUR, int)
    assert isinstance(DAILY_BAR_FETCH_MINUTE, int)
    assert MARKET_CLOSE_HOUR == 16
    assert MARKET_CLOSE_MINUTE == 0
    assert DAILY_BAR_FETCH_HOUR == 16
    assert DAILY_BAR_FETCH_MINUTE == 5
