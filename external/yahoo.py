from datetime import datetime

import yfinance as yf


def fetch_daily_bars(symbol: str, start: str, end: str) -> list[dict]:
    """
    Fetch daily OHLCV bars for a symbol from Yahoo Finance.

    Parameters
    ----------
    symbol : str  ticker symbol, e.g. "AAPL"
    start  : str  ISO date string, inclusive, e.g. "2020-01-01"
    end    : str  ISO date string, exclusive, e.g. "2022-01-01"

    Returns
    -------
    list[dict]  each dict: timestamp (datetime), open, high, low, close, volume (float)

    Raises
    ------
    ValueError  if the ticker is unknown or the date range returns no data
    """
    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start, end=end)
    if df.empty:
        raise ValueError(
            f"No data returned for symbol '{symbol}' between {start} and {end}. "
            "The ticker may be invalid or the date range may produce no results."
        )
    result: list[dict] = []
    for ts, row in df.iterrows():
        result.append({
            "timestamp": ts.to_pydatetime().replace(tzinfo=None),
            "open":      float(row["Open"]),
            "high":      float(row["High"]),
            "low":       float(row["Low"]),
            "close":     float(row["Close"]),
            "volume":    float(row["Volume"]),
        })
    return result
