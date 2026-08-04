"""Can the momentum crash be fixed?

Long-only NSE momentum earns +18.8%/yr against a +10.7% benchmark, but with a
-45.5% drawdown that almost nobody would sit through. Momentum crashes are a
documented phenomenon: they happen when a beaten-down market rebounds violently
and the losers the strategy is underweight rip upwards.

Two standard remedies, both decided in advance:

  MARKET FILTER   hold the book only while the market is above its 200-day
                  average; otherwise sit in cash. Momentum crashes occur almost
                  exclusively in down markets, so this should remove them
                  wholesale rather than trimming them.

  VOL SCALING     scale exposure by target_vol / trailing realised vol of the
                  strategy itself. Crashes are preceded by high strategy
                  volatility, so this de-risks into them.

Everything uses only data available at the rebalance date -- the market state is
read from the close of the formation date, and the position it implies is held
over the following month.
"""

import numpy as np
import pandas as pd


def market_index(px, turnover, n_universe=500, lookback=60):
    """Daily equal-weight index of the liquid universe, rebuilt monthly.

    Not a published index -- deliberately the same universe the strategy trades,
    so the filter is measuring the market the strategy is actually exposed to.
    """
    rets = px.pct_change(fill_method=None)
    month_ends = list(pd.Series(index=px.index, data=1).resample("ME").last().index)
    members, series = None, {}
    for d in px.index:
        if members is None or d in month_ends:
            hist = turnover.loc[:d].tail(lookback)
            if not hist.empty:
                med = hist.median()
                med = med[med > 0].dropna()
                members = list(med.sort_values(ascending=False).head(n_universe).index)
        if not members:
            continue
        r = rets.loc[d, [m for m in members if m in rets.columns]].replace([np.inf, -np.inf], np.nan).dropna()
        if len(r) >= 30:
            series[d] = r.mean()
    s = pd.Series(series).sort_index()
    return (1 + s).cumprod()


def market_on(index, date, ma=200):
    """True if the index closed above its `ma`-day average on `date`."""
    h = index.loc[:date]
    if len(h) < ma:
        return True                     # not enough history -> stay invested
    return bool(h.iloc[-1] > h.tail(ma).mean())


def apply_overlays(monthly, index, use_filter=True, use_volscale=False,
                   target_vol=0.15, vol_lookback=12, ma=200):
    """Return the monthly series after the chosen overlays.

    `monthly` must be a DataFrame indexed by the month-END date with a `net`
    column (the strategy's realised monthly return) and a `formed` column (the
    date the book was formed, i.e. when the decision could be made).
    """
    out, exposures = [], []
    hist = []
    for d, row in monthly.iterrows():
        exp = 1.0
        if use_filter and not market_on(index, row["formed"], ma):
            exp = 0.0
        if use_volscale and len(hist) >= vol_lookback:
            realised = np.std(hist[-vol_lookback:], ddof=1) * np.sqrt(12)
            if realised > 0:
                exp *= min(1.0, target_vol / realised)
        r = row["net"] * exp
        out.append(r)
        exposures.append(exp)
        hist.append(row["net"])          # scale on the UNSCALED history
    return pd.Series(out, index=monthly.index), pd.Series(exposures, index=monthly.index)


def stats(r):
    r = r.dropna()
    if len(r) < 6:
        return {}
    ann = (1 + r).prod() ** (12 / len(r)) - 1
    vol = r.std() * np.sqrt(12)
    eq = (1 + r).cumprod()
    dd = (eq / eq.cummax() - 1)
    return {"n": len(r), "ann": ann, "vol": vol, "sharpe": ann / vol if vol else 0.0,
            "maxdd": float(dd.min()), "hit": float((r > 0).mean()),
            "worst_month": float(r.min()), "mean": float(r.mean()), "sd": float(r.std())}
