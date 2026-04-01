"""
DefaultResultWriter — concrete BacktestResultWriter.

Writes data files (parquet by default, csv optional) and jpg plots to a
results directory after each backtest run.

Constructed with everything except the portfolio (which is only available
after the run completes):

    writer = DefaultResultWriter(
        initial_capital = 10_000.0,
        symbol_bars     = data.symbol_bars,   # {symbol: (dates, closes)}
        results_dir     = "results",
        fmt             = "parquet",           # or "csv"
    )

Then injected into Backtester which calls writer.write(portfolio) at the
end of run().

Output files
------------
  equity_curve.{ext}    — timestamp, cash, holdings, market_value, equity
  strategy_pnl.{ext}    — timestamp, {strategy_id: cumulative_realized_pnl}
  summary_metrics.{ext} — single-row table of key performance stats
  equity_curve.jpg
  drawdown.jpg
  trades.jpg
  strategy_pnl.jpg      — only if multiple strategies present
"""

import os

import matplotlib
matplotlib.use("Agg")
import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import pandas as pd

from trading.base.portfolio import Portfolio
from trading.base.result_writer import BacktestResultWriter


class DefaultResultWriter(BacktestResultWriter):
    def __init__(
        self,
        initial_capital: float,
        symbol_bars:     dict,           # {symbol: (list[datetime], list[float])}
        results_dir:     str   = "results",
        fmt:             str   = "parquet",  # "parquet" or "csv"
    ):
        self._initial_capital = initial_capital
        self._symbol_bars     = symbol_bars
        self._dir             = results_dir
        self._fmt             = fmt

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def write(self, portfolio: Portfolio) -> None:
        curve = portfolio.equity_curve
        if not curve:
            print("No trades — nothing to write.")
            return

        os.makedirs(self._dir, exist_ok=True)

        self._write_equity_curve(curve)
        self._write_strategy_pnl(portfolio.strategy_pnl)
        strategy_metrics = self._write_strategy_metrics(
            portfolio.strategy_pnl,
            portfolio.strategy_traded_value,
        )
        metrics = self._write_summary_metrics(curve)
        self._print_summary(metrics, portfolio.strategy_pnl, strategy_metrics)

        self._plot_equity_curve(curve)
        self._plot_drawdown(curve)
        self._plot_trades(curve)
        self._plot_strategy_pnl(portfolio.strategy_pnl, curve, strategy_metrics)

    # ------------------------------------------------------------------
    # File helpers
    # ------------------------------------------------------------------

    def _file_path(self, name: str, plot: bool = False) -> str:
        ext = "jpg" if plot else self._fmt
        return os.path.join(self._dir, f"{name}.{ext}")

    def _save_df(self, df: pd.DataFrame, name: str) -> str:
        path = self._file_path(name)
        if self._fmt == "parquet":
            df.to_parquet(path, index=False)
        else:
            df.to_csv(path, index=False)
        return path

    # ------------------------------------------------------------------
    # Data writers
    # ------------------------------------------------------------------

    def _write_equity_curve(self, curve: list[dict]) -> str:
        df = pd.DataFrame([
            {
                "timestamp":    row["timestamp"],
                "cash":         row["cash"],
                "holdings":     str(row["holdings"]),
                "market_value": row["market_value"],
                "equity":       row["equity"],
            }
            for row in curve
        ])
        path = self._save_df(df, "equity_curve")
        print(f"Equity curve    : {path}")
        return path

    def _write_strategy_pnl(self, strategy_pnl: list[dict]) -> None:
        if not strategy_pnl:
            return
        strategy_ids = [k for k in strategy_pnl[-1] if k != "timestamp"]
        if not strategy_ids:
            return
        df = pd.DataFrame(strategy_pnl)
        path = self._save_df(df, "strategy_pnl")
        print(f"Strategy PnL    : {path}")

    def _write_strategy_metrics(
        self,
        strategy_pnl:          list[dict],
        strategy_traded_value: dict[str, float],
    ) -> list[dict]:
        rows = self._compute_strategy_metrics(strategy_pnl, strategy_traded_value)
        if not rows:
            return rows
        path = self._save_df(pd.DataFrame(rows), "strategy_metrics")
        print(f"Strategy metrics: {path}")
        return rows

    def _compute_strategy_metrics(
        self,
        strategy_pnl:          list[dict],
        strategy_traded_value: dict[str, float],
    ) -> list[dict]:
        if not strategy_pnl:
            return []
        strategy_ids = [k for k in strategy_pnl[-1] if k != "timestamp"]
        if not strategy_ids:
            return []

        ic    = self._initial_capital
        t0    = strategy_pnl[0]["timestamp"]
        t1    = strategy_pnl[-1]["timestamp"]
        years = max((t1 - t0).days / 365.25, 1e-9)

        rows = []
        for sid in strategy_ids:
            pnl_series = [row.get(sid, 0.0) for row in strategy_pnl]
            returns = [
                (pnl_series[i] - pnl_series[i - 1]) / ic
                for i in range(1, len(pnl_series))
            ]

            sharpe  = float("nan")
            sortino = float("nan")
            if len(returns) > 1:
                n     = len(returns)
                avg_r = sum(returns) / n
                var_r = sum((r - avg_r) ** 2 for r in returns) / n
                std_r = var_r ** 0.5
                if std_r:
                    sharpe = avg_r / std_r * (252 ** 0.5)

                neg = [r for r in returns if r < 0]
                if neg:
                    down_var = sum(r ** 2 for r in neg) / n  # population semi-variance
                    down_std = down_var ** 0.5
                    if down_std:
                        sortino = avg_r / down_std * (252 ** 0.5)

            traded   = strategy_traded_value.get(sid, 0.0)
            turnover = traded / ic / years if ic else float("nan")

            final_pnl  = pnl_series[-1] if pnl_series else 0.0
            total_ret  = final_pnl / ic * 100 if ic else float("nan")
            cagr       = ((1 + final_pnl / ic) ** (1 / years) - 1) * 100 if ic else float("nan")

            peak   = 0.0
            max_dd = 0.0
            for pnl in pnl_series:
                peak   = max(peak, pnl)
                max_dd = min(max_dd, (pnl - peak) / ic * 100 if ic else 0.0)

            rows.append({
                "strategy_id":      sid,
                "total_return_pct": total_ret,
                "cagr_pct":         cagr,
                "max_drawdown_pct": max_dd,
                "sharpe":           sharpe,
                "sortino":          sortino,
                "turnover_rate":    turnover,
            })

        return rows

    def _write_summary_metrics(self, curve: list[dict]) -> dict:
        equity     = [r["equity"] for r in curve]
        timestamps = [r["timestamp"] for r in curve]
        ic         = self._initial_capital

        final      = equity[-1]
        total_ret  = (final / ic - 1) * 100
        num_days   = (timestamps[-1] - timestamps[0]).days
        years      = max(num_days / 365.25, 1e-9)
        cagr       = ((final / ic) ** (1 / years) - 1) * 100

        peak = ic
        drawdowns = []
        for e in equity:
            peak = max(peak, e)
            drawdowns.append((e - peak) / peak * 100)
        max_dd = min(drawdowns)

        fill_returns = [(equity[i] - equity[i - 1]) / equity[i - 1] for i in range(1, len(equity))]
        if len(fill_returns) > 1:
            avg_r  = sum(fill_returns) / len(fill_returns)
            var_r  = sum((r - avg_r) ** 2 for r in fill_returns) / len(fill_returns)
            sharpe = (avg_r / var_r ** 0.5) if var_r else float("nan")
        else:
            sharpe = float("nan")

        metrics = {
            "initial_capital":  ic,
            "final_equity":     final,
            "total_return_pct": total_ret,
            "cagr_pct":         cagr,
            "max_drawdown_pct": max_dd,
            "sharpe_fills":     sharpe,
            "num_fills":        len(curve),
        }
        path = self._save_df(pd.DataFrame([metrics]), "summary_metrics")
        print(f"Summary metrics : {path}")
        return metrics

    # ------------------------------------------------------------------
    # Console summary
    # ------------------------------------------------------------------

    def _print_summary(
        self,
        metrics:          dict,
        strategy_pnl:     list[dict],
        strategy_metrics: list[dict],
    ) -> None:
        ic = metrics["initial_capital"]
        print()
        print(f"Initial capital : ${ic:>10,.2f}")
        print(f"Final equity    : ${metrics['final_equity']:>10,.2f}")
        print(f"Total return    : {metrics['total_return_pct']:>+.2f}%")
        print(f"Trades (fills)  : {metrics['num_fills']}")

        if strategy_pnl:
            final_row = strategy_pnl[-1]
            ids = [k for k in final_row if k != "timestamp"]
            if ids:
                print("\nStrategy realized PnL:")
                for sid in sorted(ids):
                    print(f"  {sid:<30} ${final_row[sid]:>+10,.2f}")

        if strategy_metrics:
            print("\nStrategy metrics (per-fill returns, annualised ×√252):")
            for row in strategy_metrics:
                sid      = row["strategy_id"]
                ret      = row["total_return_pct"]
                cagr     = row["cagr_pct"]
                max_dd   = row["max_drawdown_pct"]
                sharpe   = row["sharpe"]
                sortino  = row["sortino"]
                turnover = row["turnover_rate"]
                sharpe_s  = f"{sharpe:>6.2f}"  if sharpe  == sharpe  else "   nan"
                sortino_s = f"{sortino:>6.2f}" if sortino == sortino  else "   nan"
                print(
                    f"  {sid:<30}  ret={ret:>+7.2f}%  cagr={cagr:>+7.2f}%"
                    f"  maxdd={max_dd:>7.2f}%  sharpe={sharpe_s}"
                    f"  sortino={sortino_s}  turnover={turnover:.1f}×/yr"
                )

    # ------------------------------------------------------------------
    # Plots
    # ------------------------------------------------------------------

    def _plot_equity_curve(self, curve: list[dict]) -> None:
        dates  = [r["timestamp"] for r in curve]
        equity = [r["equity"] for r in curve]
        ic     = self._initial_capital
        final  = equity[-1]
        ret    = (final / ic - 1) * 100

        fig, ax = plt.subplots(figsize=(13, 4))
        ax.plot(dates, equity, color="steelblue", linewidth=1.5, label="Equity")
        ax.axhline(ic, color="gray", linewidth=0.8, linestyle="--", label="Initial capital")
        _fmt_x(ax)
        ax.set_title(f"Equity Curve   |   Return: {ret:+.2f}%   |   Final: ${final:,.2f}")
        ax.set_ylabel("Portfolio Value ($)")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        _save_fig(fig, self._file_path("equity_curve", plot=True))
        print(f"Plot: equity curve  → {self._file_path('equity_curve', plot=True)}")

    def _plot_drawdown(self, curve: list[dict]) -> None:
        dates  = [r["timestamp"] for r in curve]
        equity = [r["equity"] for r in curve]
        ic     = self._initial_capital

        peak = ic
        drawdown = []
        for e in equity:
            peak = max(peak, e)
            drawdown.append((e - peak) / peak * 100)
        max_dd = min(drawdown)

        fig, ax = plt.subplots(figsize=(13, 3))
        ax.fill_between(dates, drawdown, 0, color="crimson", alpha=0.4)
        ax.plot(dates, drawdown, color="crimson", linewidth=0.8)
        ax.axhline(max_dd, color="darkred", linewidth=0.8, linestyle="--",
                   label=f"Max drawdown: {max_dd:.2f}%")
        _fmt_x(ax)
        ax.set_title("Drawdown (%)")
        ax.set_ylabel("Drawdown (%)")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        _save_fig(fig, self._file_path("drawdown", plot=True))
        print(f"Plot: drawdown      → {self._file_path('drawdown', plot=True)}")

    def _plot_trades(self, curve: list[dict]) -> None:
        COLORS      = ["steelblue", "darkorange", "green", "purple", "brown"]
        fill_dates  = [r["timestamp"] for r in curve]
        holdings_ls = [r["holdings"] for r in curve]
        symbols     = sorted(self._symbol_bars.keys())

        fig, ax = plt.subplots(figsize=(13, 5))
        total_buys = total_sells = 0

        for idx, symbol in enumerate(symbols):
            color = COLORS[idx % len(COLORS)]
            sym_dates, sym_closes = self._symbol_bars[symbol]
            ax.plot(sym_dates, sym_closes, color=color, linewidth=1, label=f"{symbol} close")

            price_by_date = dict(zip(sym_dates, sym_closes))
            buy_dates, buy_prices   = [], []
            sell_dates, sell_prices = [], []

            for i, (d, h) in enumerate(zip(fill_dates, holdings_ls)):
                prev_h   = holdings_ls[i - 1] if i > 0 else {}
                cur_qty  = h.get(symbol, 0)
                prev_qty = prev_h.get(symbol, 0) if isinstance(prev_h, dict) else 0
                price    = price_by_date.get(d)
                if price is None:
                    continue
                if prev_qty == 0 and cur_qty > 0:
                    buy_dates.append(d);  buy_prices.append(price)
                elif prev_qty > 0 and cur_qty == 0:
                    sell_dates.append(d); sell_prices.append(price)

            if buy_dates:
                ax.scatter(buy_dates,  buy_prices,  marker="^", color="green", s=80,
                           zorder=5, label=f"{symbol} buy")
            if sell_dates:
                ax.scatter(sell_dates, sell_prices, marker="v", color="red",   s=80,
                           zorder=5, label=f"{symbol} sell")
            total_buys  += len(buy_dates)
            total_sells += len(sell_dates)

        _fmt_x(ax)
        ax.set_title(f"Price Chart with Trade Markers   |   {total_buys} buys, {total_sells} sells")
        ax.set_ylabel("Price ($)")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        _save_fig(fig, self._file_path("trades", plot=True))
        print(f"Plot: trades        → {self._file_path('trades', plot=True)}")

    def _plot_strategy_pnl(
        self,
        strategy_pnl:     list[dict],
        curve:            list[dict],
        strategy_metrics: list[dict],
    ) -> None:
        if not strategy_pnl:
            return
        strategy_ids = [k for k in strategy_pnl[-1] if k != "timestamp"]
        if not strategy_ids:
            return

        metrics_by_id = {row["strategy_id"]: row for row in strategy_metrics}

        COLORS     = ["steelblue", "darkorange", "green", "purple", "brown"]
        fill_dates = [r["timestamp"] for r in curve]

        fig, ax = plt.subplots(figsize=(13, 4))
        for idx, sid in enumerate(strategy_ids):
            values = [row.get(sid, 0.0) for row in strategy_pnl]
            m = metrics_by_id.get(sid)
            if m:
                label = (
                    f"{sid}  "
                    f"ret={m['total_return_pct']:+.1f}%  "
                    f"cagr={m['cagr_pct']:+.1f}%  "
                    f"maxdd={m['max_drawdown_pct']:.1f}%"
                )
            else:
                label = sid
            ax.plot(fill_dates, values, color=COLORS[idx % len(COLORS)],
                    linewidth=1.5, label=label)

        ax.axhline(0, color="gray", linewidth=0.8, linestyle="--")
        _fmt_x(ax)
        ax.set_title("Per-Strategy Realized PnL")
        ax.set_ylabel("Cumulative Realized PnL ($)")
        ax.legend()
        ax.grid(axis="y", alpha=0.3)
        _save_fig(fig, self._file_path("strategy_pnl", plot=True))
        print(f"Plot: strategy PnL  → {self._file_path('strategy_pnl', plot=True)}")


# ------------------------------------------------------------------
# Module-level helpers
# ------------------------------------------------------------------

def _fmt_x(ax) -> None:
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %Y"))
    ax.xaxis.set_major_locator(mdates.MonthLocator(interval=3))
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")


def _save_fig(fig, path: str) -> None:
    plt.tight_layout()
    fig.savefig(path, dpi=150)
    plt.close(fig)
