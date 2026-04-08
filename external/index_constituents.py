import csv
import io
import os
import urllib.request
from datetime import datetime


_BASE_URL = "https://yfiua.github.io/index-constituents"


def _iter_months(start_dt: datetime, end_dt: datetime):
    year = start_dt.year
    month = start_dt.month
    while (year, month) <= (end_dt.year, end_dt.month):
        yield year, month
        month += 1
        if month > 12:
            month = 1
            year += 1


def _next_month_date(year: int, month: int) -> str:
    month += 1
    if month > 12:
        year += 1
        month = 1
    return f"{year:04d}-{month:02d}-01"


def fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
    output_path: str = "data/universe_manifest.csv",
) -> str:
    start_dt = datetime.fromisoformat(start)
    end_dt = datetime.fromisoformat(end)
    history: dict[str, dict[str, tuple[int, int]]] = {}
    fetched_months: list[tuple[int, int]] = []

    for year, month in _iter_months(start_dt, end_dt):
        url = f"{_BASE_URL}/{year:04d}/{month:02d}/constituents-{index_code}.csv"
        try:
            with urllib.request.urlopen(url) as response:
                content = response.read().decode()
        except Exception:
            continue

        fetched_months.append((year, month))

        reader = csv.DictReader(io.StringIO(content))
        for row in reader:
            symbol = row["Symbol"]
            if symbol not in history:
                history[symbol] = {"enter": (year, month), "last_seen": (year, month)}
            else:
                history[symbol]["last_seen"] = (year, month)

    if not history:
        raise ValueError(
            f"No constituent data found for index '{index_code}' in [{start}, {end}]."
        )

    last_fetched_ym = max(fetched_months)

    rows = []
    for symbol, info in sorted(history.items()):
        enter_year, enter_month = info["enter"]
        last_year, last_month = info["last_seen"]
        exit_date = ""
        if (last_year, last_month) < last_fetched_ym:
            exit_date = _next_month_date(last_year, last_month)
        rows.append(
            {
                "symbol": symbol,
                "enter_date": f"{enter_year:04d}-{enter_month:02d}-01",
                "exit_date": exit_date,
            }
        )

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    with open(output_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["symbol", "enter_date", "exit_date"])
        writer.writeheader()
        writer.writerows(rows)

    return output_path


def load_or_fetch_universe_manifest(
    index_code: str,
    start: str,
    end: str,
    output_path: str = "data/universe_manifest.csv",
    reload: bool = False,
) -> str:
    if not reload and os.path.exists(output_path):
        return output_path
    return fetch_universe_manifest(index_code, start, end, output_path)
