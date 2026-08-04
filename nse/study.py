"""Cross-sectional equity factors on the NSE point-in-time panel.

Method, fixed before any result is seen:

  universe   at each rebalance, the N most liquid names by trailing 60-day
             median turnover, chosen using ONLY data up to that date. Names
             that later delist stay in the sample until they stop trading.
  signal     ranked cross-sectionally within that universe
  portfolio  top decile minus bottom decile, equal weighted, monthly rebalance
  timing     ranks from the close of the rebalance date, returns start the NEXT
             day -- the decile spread cannot see the day it is formed
  costs      35bps per side (brokerage + STT + stamp + impact), charged on the
             fraction of the book that actually turns over

The long-short spread is the honest test: a long-only Indian equity book in
2019-2026 makes money because the market did, which says nothing about the
signal. Long-only vs an equal-weight benchmark is reported alongside so the
beta contribution is visible rather than hidden.
"""

import numpy as np
import pandas as pd

COST_BPS = 35.0
DECILE = 0.10


def liquid_universe(turnover, date, n=500, lookback=60):
    """N most liquid names as of `date`, using only prior data."""
    hist = turnover.loc[:date].tail(lookback)
    if hist.empty:
        return []
    med = hist.median()
    med = med[med > 0].dropna()
    return list(med.sort_values(ascending=False).head(n).index)


def rebalance_dates(index, freq="ME"):
    return list(pd.Series(index=index, data=1).resample(freq).last().index)


def signal_momentum(px, date, skip=21, look=252):
    """12-1 month return: the standard cross-sectional momentum definition."""
    h = px.loc[:date]
    if len(h) < look + skip:
        return None
    end = h.iloc[-1 - skip]
    start = h.iloc[-1 - skip - look] if len(h) > look + skip else None
    if start is None:
        return None
    return (end / start - 1.0)


def signal_lowvol(px, date, look=126):
    h = px.loc[:date].tail(look + 1)
    if len(h) < look // 2:
        return None
    r = h.pct_change(fill_method=None)
    v = r.std()
    return -v            # low vol ranks high


def signal_reversal(px, date, look=21):
    h = px.loc[:date]
    if len(h) < look + 1:
        return None
    return -(h.iloc[-1] / h.iloc[-1 - look] - 1.0)   # losers rank high


SIGNALS = {"momentum": signal_momentum, "lowvol": signal_lowvol, "reversal": signal_reversal}


def run(px, turnover, signal="momentum", n_universe=500, start=None, end=None):
    """Monthly long-short decile spread. Returns a dict of series and stats."""
    fn = SIGNALS[signal]
    dates = [d for d in rebalance_dates(px.index) if d in px.index]
    if start:
        dates = [d for d in dates if d >= pd.Timestamp(start)]
    if end:
        dates = [d for d in dates if d <= pd.Timestamp(end)]

    rows, prev_long, prev_short = [], set(), set()
    for i, d in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        uni = liquid_universe(turnover, d, n_universe)
        if len(uni) < 100:
            continue
        sig = fn(px[uni], d)
        if sig is None:
            continue
        sig = sig.replace([np.inf, -np.inf], np.nan).dropna()
        if len(sig) < 100:
            continue

        k = max(10, int(len(sig) * DECILE))
        ranked = sig.sort_values(ascending=False)
        longs, shorts = list(ranked.index[:k]), list(ranked.index[-k:])

        # forward return, strictly after the formation date
        fwd = px.loc[d:nxt]
        if len(fwd) < 2:
            continue
        held = fwd.iloc[1:]
        r_long = (held[longs].iloc[-1] / held[longs].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
        r_short = (held[shorts].iloc[-1] / held[shorts].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
        r_uni = (held[uni].iloc[-1] / held[uni].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
        if r_long.empty or r_short.empty:
            continue

        turn_l = len(set(longs) - prev_long) / max(1, len(longs))
        turn_s = len(set(shorts) - prev_short) / max(1, len(shorts))
        cost = (turn_l + turn_s) * (COST_BPS / 10000.0)
        prev_long, prev_short = set(longs), set(shorts)

        rows.append({
            "date": nxt, "long": r_long.mean(), "short": r_short.mean(),
            "spread": r_long.mean() - r_short.mean() - cost,
            "long_only_excess": r_long.mean() - r_uni.mean() - turn_l * (COST_BPS / 10000.0),
            "benchmark": r_uni.mean(), "n": len(sig), "cost": cost,
        })

    df = pd.DataFrame(rows).set_index("date")
    return df


def stats(df, col="spread"):
    r = df[col].dropna()
    if len(r) < 6:
        return {"n": len(r)}
    ann = (1 + r).prod() ** (12 / len(r)) - 1
    vol = r.std() * np.sqrt(12)
    eq = (1 + r).cumprod()
    return {"n": len(r), "mean_monthly": r.mean(), "sd_monthly": r.std(),
            "ann_return": ann, "ann_vol": vol, "sharpe": ann / vol if vol else 0.0,
            "hit_rate": float((r > 0).mean()), "max_dd": float((eq / eq.cummax() - 1).min()),
            "t_stat": r.mean() / (r.std() / np.sqrt(len(r)))}
