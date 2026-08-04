"""Is the NSE momentum spread just small-cap / illiquidity premium?

The worry is concrete: the short leg of a momentum book tends to fill with
beaten-down microcaps. If those names are simply small and hard to trade, the
"momentum spread" is really a size premium plus an illiquidity premium, neither
of which is a momentum edge -- and both of which are far harder to harvest than
a backtest implies.

Four independent attacks, because one is easy to fool:

  1. COMPOSITION   where do the legs sit in the liquidity distribution?
  2. WITHIN-BUCKET run momentum separately inside liquidity terciles. If it only
                   works in the small bucket, it is a size story.
  3. LARGE-CAP     restrict the whole universe to the 200 most liquid names.
                   Survives there -> not an illiquidity artefact.
  4. REGRESSION    regress the spread on a size factor built from the same
                   panel. A surviving intercept is momentum net of size.

Turnover is the size proxy: bhavcopy carries no market cap, and turnover
conflates size with liquidity -- which is fine here, since both are exactly
what we are trying to rule out.
"""

import numpy as np
import pandas as pd

from . import study


def _prep(px, turnover, date, n_universe):
    uni = study.liquid_universe(turnover, date, n_universe)
    if len(uni) < 100:
        return None, None
    sig = study.signal_momentum(px[uni], date)
    if sig is None:
        return None, None
    sig = sig.replace([np.inf, -np.inf], np.nan).dropna()
    return (sig if len(sig) >= 100 else None), uni


def composition(px, turnover, n_universe=500):
    """Liquidity percentile of the long and short legs at each rebalance."""
    dates = [d for d in study.rebalance_dates(px.index) if d in px.index]
    rows = []
    for d in dates[:-1]:
        sig, uni = _prep(px, turnover, d, n_universe)
        if sig is None:
            continue
        med = turnover.loc[:d].tail(60).median()[sig.index].dropna()
        if med.empty:
            continue
        pct = med.rank(pct=True)
        k = max(10, int(len(sig) * study.DECILE))
        ranked = sig.sort_values(ascending=False)
        longs = [s for s in ranked.index[:k] if s in pct.index]
        shorts = [s for s in ranked.index[-k:] if s in pct.index]
        if not longs or not shorts:
            continue
        rows.append({"date": d,
                     "long_liq_pct": pct[longs].mean(),
                     "short_liq_pct": pct[shorts].mean(),
                     "long_turnover": med[longs].median(),
                     "short_turnover": med[shorts].median()})
    return pd.DataFrame(rows).set_index("date")


def within_buckets(px, turnover, n_universe=500, n_buckets=3):
    """Momentum spread computed INSIDE each liquidity bucket."""
    dates = [d for d in study.rebalance_dates(px.index) if d in px.index]
    out = {b: [] for b in range(n_buckets)}
    for i, d in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        sig, uni = _prep(px, turnover, d, n_universe)
        if sig is None:
            continue
        med = turnover.loc[:d].tail(60).median()[sig.index].dropna()
        common = sig.index.intersection(med.index)
        if len(common) < 90:
            continue
        sig, med = sig[common], med[common]
        labels = pd.qcut(med.rank(method="first"), n_buckets, labels=False)
        fwd = px.loc[d:nxt]
        if len(fwd) < 2:
            continue
        held = fwd.iloc[1:]
        for b in range(n_buckets):
            names = list(labels[labels == b].index)
            if len(names) < 30:
                continue
            s = sig[names].sort_values(ascending=False)
            k = max(5, int(len(s) * study.DECILE))
            L, S = list(s.index[:k]), list(s.index[-k:])
            rl = (held[L].iloc[-1] / held[L].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
            rs = (held[S].iloc[-1] / held[S].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
            if rl.empty or rs.empty:
                continue
            out[b].append({"date": nxt, "spread": rl.mean() - rs.mean() - 2 * study.COST_BPS / 10000.0})
    return {b: pd.DataFrame(v).set_index("date") for b, v in out.items() if v}


def size_factor(px, turnover, n_universe=500):
    """Small-minus-big built from the same panel: bottom-half minus top-half turnover."""
    dates = [d for d in study.rebalance_dates(px.index) if d in px.index]
    rows = []
    for i, d in enumerate(dates[:-1]):
        nxt = dates[i + 1]
        uni = study.liquid_universe(turnover, d, n_universe)
        if len(uni) < 100:
            continue
        med = turnover.loc[:d].tail(60).median()[uni].dropna()
        if len(med) < 100:
            continue
        order = med.sort_values()
        half = len(order) // 2
        small, big = list(order.index[:half]), list(order.index[half:])
        fwd = px.loc[d:nxt]
        if len(fwd) < 2:
            continue
        held = fwd.iloc[1:]
        rs = (held[small].iloc[-1] / held[small].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
        rb = (held[big].iloc[-1] / held[big].iloc[0] - 1).replace([np.inf, -np.inf], np.nan).dropna()
        if rs.empty or rb.empty:
            continue
        rows.append({"date": nxt, "smb": rs.mean() - rb.mean(), "mkt": pd.concat([rs, rb]).mean()})
    return pd.DataFrame(rows).set_index("date")


def regress(spread, factors):
    """OLS of the momentum spread on [1, SMB, MKT]. Intercept = momentum net of size."""
    d = pd.concat([spread.rename("y"), factors], axis=1, join="inner").dropna()
    y = d["y"].values
    X = np.column_stack([np.ones(len(d)), d["smb"], d["mkt"]])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    se = np.sqrt(np.diag((resid @ resid / dof) * np.linalg.inv(X.T @ X)))
    return {"alpha_monthly": beta[0], "t_alpha": beta[0] / se[0],
            "beta_smb": beta[1], "t_smb": beta[1] / se[1],
            "beta_mkt": beta[2], "n": len(d)}
