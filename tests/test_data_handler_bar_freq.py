# tests/test_data_handler_bar_freq.py
from unittest.mock import MagicMock


def test_alpaca_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.alpaca_data_handler import AlpacaDataHandler
    handler = AlpacaDataHandler(
        emit=MagicMock(), symbols=["AAPL"], bar_freq="5m",
        api_key="k", secret="s",
    )
    assert handler.bar_freq == "5m"


def test_yahoo_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.yahoo_data_handler import YahooDataHandler
    handler = YahooDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-10",
        fetch=lambda syms, s, e, freq="1d": {"AAPL": []},
        bar_freq="1d",
    )
    assert handler.bar_freq == "1d"


def test_multi_csv_data_handler_exposes_bar_freq():
    from trading.impl.data_handler.multi_csv_data_handler import MultiCSVDataHandler
    handler = MultiCSVDataHandler(
        emit=MagicMock(),
        symbols=["AAPL"],
        start="2020-01-01",
        end="2020-01-05",
        bar_freq="5m",
    )
    assert handler.bar_freq == "5m"


def test_data_handler_default_bar_freq_is_1d():
    from trading.base.data import DataHandler

    class _MinimalHandler(DataHandler):
        def prefill(self): pass
        def update_bars(self): return False
        def get_latest_bars(self, symbol, n=1): return []

    handler = _MinimalHandler(emit=MagicMock())   # no bar_freq → defaults to "1d"
    assert handler.bar_freq == "1d"
