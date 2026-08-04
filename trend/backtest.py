"""Backtest engine and performance statistics."""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import strategy as st

TRADING_DAYS = 252


@dataclass
class Config:
    signal: str = "multiscale"
    signal_kwargs: dict = field(default_factory=dict)
    rebalance: str = "M"              # 'M' monthly, 'W' weekly, 'D' daily
    asset_vol_target: float = 0.20
    portfolio_vol_target: float = 0.12
    vol_halflife: int = 60
    max_leverage: float = 3.0
    max_weight: float = 0.25
    cost_bps: float = 5.0             # per unit of turnover, one way
    use_portfolio_vol_target: bool = True


@dataclass
class Result:
    config: Config
    weights: pd.DataFrame
    returns: pd.Series          # net of costs
    gross_returns: pd.Series
    costs: pd.Series
    turnover: pd.Series
    equity: pd.Series

    @property
    def stats(self) -> dict:
        return performance_stats(self.returns)


def _rebalance_mask(index: pd.DatetimeIndex, freq: str) -> pd.Series:
    """True on the last trading day of each rebalance period."""
    if freq.upper() == "D":
        return pd.Series(True, index=index)
    periods = index.to_period({"M": "M", "W": "W"}[freq.upper()])
    is_last = pd.Series(periods, index=index).ne(
        pd.Series(periods, index=index).shift(-1)
    )
    return is_last


def run_backtest(prices: pd.DataFrame, config: Config | None = None) -> Result:
    """Run one full backtest.

    Execution model: signals and target weights are computed from the close of
    day t; the book is assumed to be traded into at the close of t and earns
    the return of t+1. That is enforced by a single ``shift(1)`` on weights --
    the one line that separates a backtest from a fantasy.
    """
    config = config or Config()
    returns = st.daily_returns(prices)

    signal_fn = st.SIGNALS[config.signal]
    signals = signal_fn(prices, **config.signal_kwargs)
    vol = st.ex_ante_volatility(returns, halflife=config.vol_halflife)

    target = st.target_weights(
        signals,
        vol,
        asset_vol_target=config.asset_vol_target,
        max_leverage=config.max_leverage,
        max_weight=config.max_weight,
    )

    if config.use_portfolio_vol_target:
        target = st.apply_portfolio_vol_target(
            target,
            returns,
            portfolio_vol_target=config.portfolio_vol_target,
            halflife=config.vol_halflife,
        )

    # Only act on rebalance dates; hold the book in between.
    mask = _rebalance_mask(prices.index, config.rebalance)
    held = target.where(mask).ffill().fillna(0.0)

    # Trade at t, earn at t+1.
    effective = held.shift(1).fillna(0.0)

    gross = (effective * returns).sum(axis=1)

    turnover = held.diff().abs().sum(axis=1).fillna(0.0)
    costs = turnover * (config.cost_bps / 10_000.0)
    net = gross - costs.shift(1).fillna(0.0)

    # Trim the warmup period where nothing is tradeable yet.
    live = effective.abs().sum(axis=1) > 0
    if live.any():
        first = live.idxmax()
        net, gross, costs, turnover = (
            net[first:],
            gross[first:],
            costs[first:],
            turnover[first:],
        )
        held = held[first:]

    equity = (1 + net.fillna(0)).cumprod()

    return Result(
        config=config,
        weights=held,
        returns=net.fillna(0),
        gross_returns=gross.fillna(0),
        costs=costs,
        turnover=turnover,
        equity=equity,
    )


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------

def drawdown_series(returns: pd.Series) -> pd.Series:
    equity = (1 + returns).cumprod()
    return equity / equity.cummax() - 1


def max_drawdown_days(returns: pd.Series) -> int:
    """Longest stretch, in calendar days, spent below a previous peak."""
    dd = drawdown_series(returns)
    underwater = dd < -1e-12
    if not underwater.any():
        return 0
    longest = current_start = None
    best = 0
    for date, is_under in underwater.items():
        if is_under and current_start is None:
            current_start = date
        elif not is_under and current_start is not None:
            best = max(best, (date - current_start).days)
            current_start = None
    if current_start is not None:
        best = max(best, (underwater.index[-1] - current_start).days)
        longest = current_start
    _ = longest
    return best


def performance_stats(returns: pd.Series) -> dict:
    r = returns.dropna()
    if r.empty:
        return {}

    years = len(r) / TRADING_DAYS
    total = (1 + r).prod()
    cagr = total ** (1 / years) - 1 if years > 0 else np.nan
    vol = r.std() * np.sqrt(TRADING_DAYS)
    sharpe = cagr / vol if vol > 0 else np.nan

    downside = r[r < 0].std() * np.sqrt(TRADING_DAYS)
    sortino = cagr / downside if downside > 0 else np.nan

    dd = drawdown_series(r)
    max_dd = dd.min()
    calmar = cagr / abs(max_dd) if max_dd < 0 else np.nan

    monthly = (1 + r).resample("ME").prod() - 1
    yearly = (1 + r).resample("YE").prod() - 1

    return {
        "start": r.index[0].date().isoformat(),
        "end": r.index[-1].date().isoformat(),
        "years": years,
        "cagr": cagr,
        "vol": vol,
        "sharpe": sharpe,
        "sortino": sortino,
        "max_dd": max_dd,
        "calmar": calmar,
        "longest_dd_days": max_drawdown_days(r),
        "monthly_win_rate": (monthly > 0).mean(),
        "worst_month": monthly.min(),
        "best_month": monthly.max(),
        "negative_months": int((monthly <= 0).sum()),
        "total_months": int(len(monthly)),
        "negative_years": int((yearly <= 0).sum()),
        "total_years": int(len(yearly)),
        "skew": r.skew(),
        "monthly_returns": monthly,
        "yearly_returns": yearly,
    }


def buy_and_hold(prices: pd.Series) -> pd.Series:
    return prices.pct_change(fill_method=None).fillna(0)


def summary_table(results: dict[str, pd.Series]) -> pd.DataFrame:
    """Compare several return streams side by side."""
    rows = {}
    for name, rets in results.items():
        s = performance_stats(rets)
        rows[name] = {
            "CAGR": s["cagr"],
            "Vol": s["vol"],
            "Sharpe": s["sharpe"],
            "Sortino": s["sortino"],
            "MaxDD": s["max_dd"],
            "Calmar": s["calmar"],
            "DD days": s["longest_dd_days"],
            "Mth win%": s["monthly_win_rate"],
            "Worst mth": s["worst_month"],
            "Neg yrs": f"{s['negative_years']}/{s['total_years']}",
        }
    return pd.DataFrame(rows).T
