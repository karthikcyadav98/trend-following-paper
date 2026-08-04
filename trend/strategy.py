"""Signal generation and volatility-based position sizing.

Every function here returns a frame aligned to the price index where row ``t``
uses only information available at the close of ``t``. The backtest engine is
responsible for the one-day execution lag -- nothing in this module peeks.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_DAYS = 252


def daily_returns(prices: pd.DataFrame) -> pd.DataFrame:
    return prices.pct_change(fill_method=None)


# --------------------------------------------------------------------------
# Signals
# --------------------------------------------------------------------------

def signal_timeseries_momentum(prices: pd.DataFrame, lookback: int = 252) -> pd.DataFrame:
    """Sign of the trailing ``lookback``-day return (Moskowitz/Ooi/Pedersen)."""
    past = prices.pct_change(lookback, fill_method=None)
    return np.sign(past).where(past.notna())


def signal_moving_average(
    prices: pd.DataFrame, fast: int = 1, slow: int = 200
) -> pd.DataFrame:
    """+1 when the fast average is above the slow average, -1 below."""
    fast_ma = prices.rolling(fast, min_periods=fast).mean()
    slow_ma = prices.rolling(slow, min_periods=slow).mean()
    diff = fast_ma - slow_ma
    return np.sign(diff).where(diff.notna())


def signal_breakout(prices: pd.DataFrame, lookback: int = 100) -> pd.DataFrame:
    """Donchian channel: long at new highs, short at new lows, hold between."""
    high = prices.rolling(lookback, min_periods=lookback).max()
    low = prices.rolling(lookback, min_periods=lookback).min()
    raw = pd.DataFrame(np.nan, index=prices.index, columns=prices.columns)
    raw[prices >= high] = 1.0
    raw[prices <= low] = -1.0
    # Hold the last state; only valid once the window is full.
    return raw.ffill().where(high.notna())


def signal_multiscale(prices: pd.DataFrame, lookbacks=(63, 126, 252)) -> pd.DataFrame:
    """Average of several momentum horizons -- less sensitive to any one choice.

    This is the honest default. Picking a single lookback because it
    backtested best is the most common way to fool yourself.
    """
    signals = [signal_timeseries_momentum(prices, lb) for lb in lookbacks]
    stacked = pd.concat(signals).groupby(level=0).mean()
    return stacked.reindex(prices.index)


SIGNALS = {
    "tsmom": signal_timeseries_momentum,
    "ma": signal_moving_average,
    "breakout": signal_breakout,
    "multiscale": signal_multiscale,
}


# --------------------------------------------------------------------------
# Sizing
# --------------------------------------------------------------------------

def ex_ante_volatility(returns: pd.DataFrame, halflife: int = 60) -> pd.DataFrame:
    """Annualised EWMA volatility using only past data."""
    vol = returns.ewm(halflife=halflife, min_periods=halflife).std()
    return vol * np.sqrt(TRADING_DAYS)


def target_weights(
    signals: pd.DataFrame,
    vol: pd.DataFrame,
    asset_vol_target: float = 0.20,
    max_leverage: float = 3.0,
    max_weight: float = 0.25,
) -> pd.DataFrame:
    """Scale each signal by inverse volatility, then normalise the book.

    Inverse-vol sizing is what makes a trend book coherent: without it, a
    position in crude oil swamps a position in 7-10y Treasuries and the
    portfolio is really a one-asset bet wearing a diversified costume.
    """
    tradeable = signals.notna() & vol.notna() & (vol > 0)
    scaled = signals * (asset_vol_target / vol)
    scaled = scaled.where(tradeable, 0.0)

    # Equal risk budget across whatever is live on that date.
    n_active = tradeable.sum(axis=1).replace(0, np.nan)
    weights = scaled.div(n_active, axis=0)

    weights = weights.clip(-max_weight, max_weight)

    # Cap gross exposure.
    gross = weights.abs().sum(axis=1)
    scale = (max_leverage / gross).clip(upper=1.0).fillna(1.0)
    weights = weights.mul(scale, axis=0)

    return weights.fillna(0.0)


def apply_portfolio_vol_target(
    weights: pd.DataFrame,
    returns: pd.DataFrame,
    portfolio_vol_target: float = 0.12,
    halflife: int = 60,
    max_scale: float = 2.0,
) -> pd.DataFrame:
    """Rescale the book so realised portfolio vol tracks the target.

    Uses the *previous* day's weights against trailing returns, so the scale
    factor for day t is knowable at t.
    """
    gross_pnl = (weights.shift(1) * returns).sum(axis=1)
    realised = gross_pnl.ewm(halflife=halflife, min_periods=halflife).std() * np.sqrt(
        TRADING_DAYS
    )
    scale = (portfolio_vol_target / realised).clip(upper=max_scale)
    scale = scale.replace([np.inf, -np.inf], np.nan).ffill().fillna(1.0)
    return weights.mul(scale, axis=0)
