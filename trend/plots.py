"""Charts: equity curve, drawdown, rolling Sharpe, monthly heatmap."""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from .backtest import drawdown_series  # noqa: E402

TRADING_DAYS = 252


def plot_report(
    streams: dict[str, pd.Series],
    strategy_name: str,
    out_path: Path,
) -> Path:
    """Four-panel tearsheet comparing the strategy against benchmarks."""
    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    fig.suptitle("Cross-asset trend following — backtest", fontsize=15, y=0.98)

    # 1. Equity, log scale.
    ax = axes[0, 0]
    for name, r in streams.items():
        equity = (1 + r.fillna(0)).cumprod()
        ax.plot(equity.index, equity.values, label=name,
                lw=1.9 if name == strategy_name else 1.1,
                alpha=1.0 if name == strategy_name else 0.65)
    ax.set_yscale("log")
    ax.set_title("Growth of $1 (log scale)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    # 2. Drawdown.
    ax = axes[0, 1]
    for name, r in streams.items():
        dd = drawdown_series(r.fillna(0))
        ax.plot(dd.index, dd.values * 100, label=name,
                lw=1.9 if name == strategy_name else 1.1,
                alpha=1.0 if name == strategy_name else 0.6)
    ax.set_title("Drawdown (%)")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    # 3. Rolling 1y Sharpe -- shows how long the bad stretches last.
    ax = axes[1, 0]
    for name, r in streams.items():
        roll = (r.rolling(TRADING_DAYS).mean() * TRADING_DAYS) / (
            r.rolling(TRADING_DAYS).std() * np.sqrt(TRADING_DAYS)
        )
        ax.plot(roll.index, roll.values, label=name,
                lw=1.6 if name == strategy_name else 1.0,
                alpha=1.0 if name == strategy_name else 0.55)
    ax.axhline(0, color="black", lw=0.8)
    ax.set_title("Rolling 12-month Sharpe")
    ax.legend(fontsize=8)
    ax.grid(alpha=0.25)

    # 4. Monthly return heatmap for the strategy.
    ax = axes[1, 1]
    r = streams[strategy_name]
    monthly = (1 + r.fillna(0)).resample("ME").prod() - 1
    table = monthly.to_frame("r")
    table["year"] = table.index.year
    table["month"] = table.index.month
    pivot = table.pivot_table(index="year", columns="month", values="r")
    lim = np.nanmax(np.abs(pivot.values)) if pivot.size else 0.1
    im = ax.imshow(pivot.values * 100, cmap="RdYlGn", aspect="auto",
                   vmin=-lim * 100, vmax=lim * 100)
    ax.set_xticks(range(len(pivot.columns)))
    ax.set_xticklabels(["J", "F", "M", "A", "M", "J", "J", "A", "S", "O", "N", "D"][
        : len(pivot.columns)
    ])
    ax.set_yticks(range(len(pivot.index)))
    ax.set_yticklabels(pivot.index, fontsize=7)
    ax.set_title(f"{strategy_name}: monthly returns (%)")
    fig.colorbar(im, ax=ax, fraction=0.03)

    fig.tight_layout(rect=(0, 0, 1, 0.96))
    out_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(out_path, dpi=120)
    plt.close(fig)
    return out_path
