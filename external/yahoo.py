import pandas as pd
import yfinance as yf


def fetch_bars(symbols: list[str], start: str, end: str, bar_freq: str = "1d") -> dict[str, list[dict]]:
    """
    Fetch OHLCV bars for one or more symbols from Yahoo Finance in a single request.

    Parameters
    ----------
    symbols  : list[str]  ticker symbols, e.g. ["AAPL", "MSFT"]
    start    : str        ISO date string, inclusive, e.g. "2020-01-01"
    end      : str        ISO date string, exclusive, e.g. "2022-01-01"
    bar_freq : str        bar interval passed to yfinance, e.g. "1d", "1h", "5m"

    Returns
    -------
    dict[str, list[dict]]  symbol -> list of dicts with keys:
                           timestamp (datetime), open, high, low, close, volume (float)

    Raises
    ------
    ValueError  if the response is empty or a symbol returns no data
    """
    df = yf.download(symbols, start=start, end=end, interval=bar_freq, auto_adjust=True, progress=False)
    if df.empty:
        raise ValueError(
            f"No data returned for symbols {symbols} between {start} and {end}."
        )

    result: dict[str, list[dict]] = {}
    for symbol in symbols:
        sym_df = df.xs(symbol, level=1, axis=1) if isinstance(df.columns, pd.MultiIndex) else df
        if sym_df.empty:
            raise ValueError(
                f"No data returned for symbol '{symbol}' between {start} and {end}."
            )
        rows = []
        for ts, row in sym_df.iterrows():
            rows.append({
                "timestamp": ts.to_pydatetime().replace(tzinfo=None),
                "open":      float(row["Open"]),
                "high":      float(row["High"]),
                "low":       float(row["Low"]),
                "close":     float(row["Close"]),
                "volume":    float(row["Volume"]),
            })
        result[symbol] = rows

    return result
