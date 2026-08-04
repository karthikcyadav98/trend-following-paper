"""Robustness checks.

A single backtest number is worthless. What matters is whether the result
survives changing the parameters, the sample period, and the cost assumption.
These checks exist to try to break the strategy, not to flatter it.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd

from .backtest import Config, performance_stats, run_backtest


def parameter_sweep(prices: pd.DataFrame, base: Config | None = None) -> pd.DataFrame:
    """Grid over the choices a researcher is most tempted to overfit."""
    base = base or Config()
    grid = {
        "signal": ["tsmom", "ma", "breakout", "multiscale"],
        "rebalance": ["M", "W"],
        "cost_bps": [2.0, 5.0, 15.0],
    }
    rows = []
    for signal, rebal, cost in itertools.product(*grid.values()):
        cfg = Config(
            signal=signal,
            rebalance=rebal,
            cost_bps=cost,
            asset_vol_target=base.asset_vol_target,
            portfolio_vol_target=base.portfolio_vol_target,
            max_leverage=base.max_leverage,
        )
        s = run_backtest(prices, cfg).stats
        rows.append(
            {
                "signal": signal,
                "rebalance": rebal,
                "cost_bps": cost,
                "CAGR": s["cagr"],
                "Sharpe": s["sharpe"],
                "MaxDD": s["max_dd"],
                "Mth win%": s["monthly_win_rate"],
            }
        )
    return pd.DataFrame(rows).sort_values("Sharpe", ascending=False)


def lookback_sensitivity(prices: pd.DataFrame, base: Config | None = None) -> pd.DataFrame:
    """Does the edge depend on one magic lookback, or is it broad?"""
    base = base or Config()
    rows = []
    for lb in [21, 42, 63, 126, 189, 252, 378, 504]:
        cfg = Config(
            signal="tsmom",
            signal_kwargs={"lookback": lb},
            rebalance=base.rebalance,
            cost_bps=base.cost_bps,
        )
        s = run_backtest(prices, cfg).stats
        rows.append(
            {
                "lookback_days": lb,
                "CAGR": s["cagr"],
                "Sharpe": s["sharpe"],
                "MaxDD": s["max_dd"],
            }
        )
    return pd.DataFrame(rows)


def subperiod_stability(prices: pd.DataFrame, config: Config | None = None) -> pd.DataFrame:
    """Split the sample into fixed blocks. Consistency across blocks is the
    only weak evidence of an edge available without out-of-sample data."""
    result = run_backtest(prices, config or Config())
    r = result.returns
    rows = []
    for period, chunk in r.groupby(pd.Grouper(freq="3YE")):
        if len(chunk) < 126:
            continue
        s = performance_stats(chunk)
        rows.append(
            {
                "period_end": period.date().isoformat(),
                "CAGR": s["cagr"],
                "Sharpe": s["sharpe"],
                "MaxDD": s["max_dd"],
            }
        )
    return pd.DataFrame(rows)


def randomised_signal_test(
    prices: pd.DataFrame, config: Config | None = None, n: int = 200, seed: int = 0
) -> dict:
    """Compare the real Sharpe against random sign-flipped signals.

    If a coin-flip book with identical vol targeting and costs matches the
    strategy, the trend signal is contributing nothing and the equity curve is
    just leverage plus luck.
    """
    from . import strategy as st

    config = config or Config()
    real = run_backtest(prices, config)
    real_sharpe = real.stats["sharpe"]

    returns = st.daily_returns(prices)
    vol = st.ex_ante_volatility(returns, halflife=config.vol_halflife)
    signals = st.SIGNALS[config.signal](prices, **config.signal_kwargs)
    tradeable = signals.notna()

    rng = np.random.default_rng(seed)
    sharpes = []
    from .backtest import _rebalance_mask

    mask = _rebalance_mask(prices.index, config.rebalance)
    rebal_dates = prices.index[mask]

    for _ in range(n):
        # One random sign per asset per rebalance date, then held.
        draws = pd.DataFrame(
            rng.choice([-1.0, 1.0], size=(len(rebal_dates), prices.shape[1])),
            index=rebal_dates,
            columns=prices.columns,
        )
        fake = draws.reindex(prices.index).ffill().where(tradeable)
        w = st.target_weights(
            fake, vol, config.asset_vol_target, config.max_leverage, config.max_weight
        )
        w = w.where(mask).ffill().fillna(0.0)
        gross = (w.shift(1).fillna(0.0) * returns).sum(axis=1)
        cost = w.diff().abs().sum(axis=1).fillna(0.0) * (config.cost_bps / 10_000)
        net = (gross - cost.shift(1).fillna(0.0)).fillna(0)
        s = performance_stats(net)
        if s:
            sharpes.append(s["sharpe"])

    sharpes = np.array([s for s in sharpes if np.isfinite(s)])
    pct = float((sharpes < real_sharpe).mean()) if len(sharpes) else np.nan
    return {
        "real_sharpe": real_sharpe,
        "random_mean_sharpe": float(sharpes.mean()) if len(sharpes) else np.nan,
        "random_p95_sharpe": float(np.percentile(sharpes, 95)) if len(sharpes) else np.nan,
        "percentile_vs_random": pct,
        "n_trials": len(sharpes),
    }
