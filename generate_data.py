"""Generate synthetic OHLCV data for backtesting — one CSV per symbol."""
import csv
import random
from datetime import date, timedelta

START    = date(2020, 1, 2)
NUM_DAYS = 756  # ~3 years of trading days

SYMBOLS = [
    {"symbol": "AAPL", "init_price": 150.0, "seed": 42},
    {"symbol": "MSFT", "init_price": 250.0, "seed":  7},
]

for cfg in SYMBOLS:
    rng   = random.Random(cfg["seed"])
    rows  = []
    price = cfg["init_price"]

    for i in range(NUM_DAYS):
        day = START + timedelta(days=i)
        if day.weekday() >= 5:          # skip weekends
            continue
        change = rng.gauss(0.0003, 0.015)
        open_  = price
        close  = round(open_ * (1 + change), 4)
        high   = round(max(open_, close) * (1 + abs(rng.gauss(0, 0.005))), 4)
        low    = round(min(open_, close) * (1 - abs(rng.gauss(0, 0.005))), 4)
        volume = int(rng.uniform(500_000, 5_000_000))
        rows.append({
            "timestamp": day.strftime("%Y-%m-%d"),
            "open":      round(open_, 4),
            "high":      high,
            "low":       low,
            "close":     close,
            "volume":    volume,
        })
        price = close

    output = f"data/{cfg['symbol']}.csv"
    with open(output, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=["timestamp","open","high","low","close","volume"])
        writer.writeheader()
        writer.writerows(rows)

    lo = min(r["close"] for r in rows)
    hi = max(r["close"] for r in rows)
    print(f"Generated {len(rows)} bars → {output}  (price range: {lo:.2f} – {hi:.2f})")
