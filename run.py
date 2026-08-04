#!/usr/bin/env python
"""Run the cross-asset trend-following backtest.

    python run.py                    # baseline backtest + tearsheet
    python run.py --robustness       # add parameter sweeps and a random-signal test
    python run.py --refresh          # re-download price data
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

from trend import data, plots, robustness
from trend.backtest import Config, buy_and_hold, performance_stats, run_backtest, summary_table

OUT = Path(__file__).resolve().parent / "output"

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 30)


def pct(x) -> str:
    return f"{x * 100:6.2f}%" if pd.notna(x) else "   n/a"


def fmt(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    for col in out.columns:
        if col in {"CAGR", "Vol", "MaxDD", "Mth win%", "Worst mth"}:
            out[col] = out[col].map(pct)
        elif col in {"Sharpe", "Sortino", "Calmar"}:
            out[col] = out[col].map(lambda v: f"{v:5.2f}" if pd.notna(v) else "  n/a")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--signal", default="multiscale", choices=["tsmom", "ma", "breakout", "multiscale"])
    ap.add_argument("--rebalance", default="M", choices=["D", "W", "M"])
    ap.add_argument("--cost-bps", type=float, default=5.0)
    ap.add_argument("--vol-target", type=float, default=0.12)
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--robustness", action="store_true")
    args = ap.parse_args()

    print("Loading price data ...")
    prices = data.load_prices(start=args.start, refresh=args.refresh)
    print(f"  {prices.shape[1]} assets, {prices.index[0].date()} -> {prices.index[-1].date()}")
    coverage = prices.notna().sum().sort_values()
    print("  history (trading days):",
          ", ".join(f"{t}={n}" for t, n in coverage.items()))

    cfg = Config(
        signal=args.signal,
        rebalance=args.rebalance,
        cost_bps=args.cost_bps,
        portfolio_vol_target=args.vol_target,
    )

    print("\nRunning backtest ...")
    res = run_backtest(prices, cfg)
    s = res.stats

    print(f"\n{'=' * 78}")
    print(f"STRATEGY: {args.signal} | rebalance={args.rebalance} | "
          f"cost={args.cost_bps}bps | vol target={args.vol_target:.0%}")
    print("=" * 78)
    print(f"  Period              {s['start']} -> {s['end']}  ({s['years']:.1f} years)")
    print(f"  CAGR                {pct(s['cagr'])}")
    print(f"  Volatility          {pct(s['vol'])}")
    print(f"  Sharpe              {s['sharpe']:.2f}")
    print(f"  Sortino             {s['sortino']:.2f}")
    print(f"  Max drawdown        {pct(s['max_dd'])}")
    print(f"  Calmar              {s['calmar']:.2f}")
    print(f"  Longest drawdown    {s['longest_dd_days']} calendar days "
          f"({s['longest_dd_days'] / 365:.1f} years)")
    print(f"  Positive months     {s['total_months'] - s['negative_months']}/"
          f"{s['total_months']}  ({pct(s['monthly_win_rate'])})")
    print(f"  Worst month         {pct(s['worst_month'])}")
    print(f"  Losing years        {s['negative_years']}/{s['total_years']}")
    print(f"  Skew                {s['skew']:.2f}")
    print(f"  Avg gross exposure  {res.weights.abs().sum(axis=1).mean():.2f}x")
    print(f"  Annual turnover     {res.turnover.sum() / s['years']:.1f}x")
    print(f"  Cost drag           {pct(res.costs.sum() / s['years'])} per year")

    # Benchmarks on the same window.
    window = res.returns.index
    streams = {"Trend": res.returns}
    if "SPY" in prices:
        streams["SPY buy & hold"] = buy_and_hold(prices["SPY"]).reindex(window).fillna(0)
    if "SPY" in prices and "IEF" in prices:
        sixty_forty = (
            0.6 * buy_and_hold(prices["SPY"]) + 0.4 * buy_and_hold(prices["IEF"])
        )
        streams["60/40"] = sixty_forty.reindex(window).fillna(0)

    print(f"\n{'-' * 78}\nVERSUS BENCHMARKS (same window)\n{'-' * 78}")
    print(fmt(summary_table(streams)).to_string())

    print(f"\n{'-' * 78}\nCALENDAR YEAR RETURNS\n{'-' * 78}")
    yearly = pd.DataFrame(
        {name: performance_stats(r)["yearly_returns"] for name, r in streams.items()}
    )
    yearly.index = yearly.index.year
    print((yearly * 100).round(1).to_string())

    path = plots.plot_report(streams, "Trend", OUT / "tearsheet.png")
    print(f"\nChart written to {path}")

    res.returns.to_frame("net_return").to_csv(OUT / "returns.csv")
    res.weights.to_csv(OUT / "weights.csv")
    print(f"Returns and weights written to {OUT}/")

    if args.robustness:
        print(f"\n{'=' * 78}\nROBUSTNESS\n{'=' * 78}")

        print("\nParameter sweep (signal x rebalance x cost):")
        sweep = robustness.parameter_sweep(prices, cfg)
        print(fmt(sweep).to_string(index=False))

        print("\nLookback sensitivity (single-horizon tsmom):")
        print(fmt(robustness.lookback_sensitivity(prices, cfg)).to_string(index=False))

        print("\n3-year subperiod stability:")
        print(fmt(robustness.subperiod_stability(prices, cfg)).to_string(index=False))

        print("\nRandom-signal test (does the trend signal beat coin flips?):")
        rt = robustness.randomised_signal_test(prices, cfg, n=200)
        print(f"  real Sharpe            {rt['real_sharpe']:.2f}")
        print(f"  random mean Sharpe     {rt['random_mean_sharpe']:.2f}")
        print(f"  random 95th pct Sharpe {rt['random_p95_sharpe']:.2f}")
        print(f"  real beats {rt['percentile_vs_random']:.1%} of {rt['n_trials']} random books")


if __name__ == "__main__":
    main()
