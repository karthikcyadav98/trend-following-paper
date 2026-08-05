"""Does excluding BTC/ETH improve the deployed trend book?

The deployed live configuration (long-only, gross capped 1.0x, per-asset cap
re-applied after vol targeting) holds crypto alongside thirteen ETFs. Crypto is
the most volatile sleeve, the shortest history, and the one an LRS investor has
to hold on a separate rail entirely -- so "would the book be better without it"
is a real deployment question, not parameter noise.

Protocol, fixed before the test runs:

  config     the DEPLOYED pipeline from live/paper.py, reproduced exactly:
             multiscale signal clipped long-only, inverse-vol sizing with
             max_leverage=1.0 / max_weight=0.25, 12% portfolio vol target,
             per-asset cap re-applied after targeting, gross renormalised to
             1.0, monthly rebalance, 5bps costs, trade at t earn t+1.
  variant    identical, with BTC-USD and ETH-USD removed from the universe.
  split      70/30 by time on the common live index. Train may be inspected;
             the verdict comes from TEST only, evaluated once.
  verdict    SUPPORTED requires BOTH: TEST Sharpe(ex-crypto) > TEST
             Sharpe(baseline), AND z of the mean daily return difference
             (ex-crypto minus baseline) over TEST clearing the
             multiple-testing bar. z > 0 below the bar is NOT SIGNIFICANT;
             z <= 0 is REJECTED. Anything short of SUPPORTED changes nothing:
             crypto stays in the book.
"""

import numpy as np
import pandas as pd

from . import journal as J, protocol as P

CRYPTO = ["BTC-USD", "ETH-USD"]
NAME = "trend.crypto_exclusion"
HYPOTHESIS = "Excluding BTC/ETH from the deployed trend book improves risk-adjusted return"
CRITERIA = ("SUPPORTED only if TEST Sharpe (ex-crypto) > TEST Sharpe (baseline) AND "
            "z of mean daily TEST return difference clears the adjusted bar; "
            "pre-registered 70/30 time split; deployed long-only 1x config")


def deployed_book(prices, exclude=(), rebalance="M", cost_bps=5.0):
    """Net daily returns of the deployed configuration on a universe.

    Mirrors live/paper.py target_book() for weights and trend/backtest.py for
    execution (rebalance mask, one-day lag, turnover costs).
    """
    from trend import strategy as st
    from trend.backtest import _rebalance_mask

    px = prices[[c for c in prices.columns if c not in exclude]]
    returns = st.daily_returns(px)
    sig = st.signal_multiscale(px).clip(lower=0)
    vol = st.ex_ante_volatility(returns, halflife=60)
    w = st.target_weights(sig, vol, asset_vol_target=0.20,
                          max_leverage=1.0, max_weight=0.25)
    w = st.apply_portfolio_vol_target(w, returns, portfolio_vol_target=0.12, halflife=60)
    w = w.clip(lower=0).clip(upper=0.25)
    gross = w.abs().sum(axis=1)
    over = gross > 1.0
    if over.any():
        w.loc[over] = w.loc[over].div(gross[over], axis=0)

    held = w.where(_rebalance_mask(px.index, rebalance)).ffill().fillna(0.0)
    effective = held.shift(1).fillna(0.0)
    gross_ret = (effective * returns).sum(axis=1)
    turnover = held.diff().abs().sum(axis=1).fillna(0.0)
    net = gross_ret - (turnover * (cost_bps / 10_000.0)).shift(1).fillna(0.0)

    live = effective.abs().sum(axis=1) > 0
    return net[live.idxmax():].fillna(0.0)


def _sharpe(r):
    if r.std() == 0:
        return 0.0
    years = len(r) / 252
    cagr = (1 + r).prod() ** (1 / years) - 1
    return cagr / (r.std() * np.sqrt(252))


def _maxdd(r):
    eq = (1 + r).cumprod()
    return float((eq / eq.cummax() - 1).min())


def run():
    if NAME in {e["name"] for e in J.entries() if e.get("kind") == "result"}:
        print(f"  {NAME} already has a recorded result -- refusing to re-run")
        return

    n_prior = J.n_tests()
    J.preregister(NAME, HYPOTHESIS, CRITERIA)

    from trend.data import load_prices
    prices = load_prices()

    base = deployed_book(prices)
    excl = deployed_book(prices, exclude=CRYPTO)
    idx = base.index.intersection(excl.index)
    base, excl = base[idx], excl[idx]

    cut = int(len(idx) * 0.70)
    tr_b, te_b = base.iloc[:cut], base.iloc[cut:]
    tr_e, te_e = excl.iloc[:cut], excl.iloc[cut:]

    diff = te_e - te_b
    v = P.evaluate(float(diff.mean()), float(diff.std()), int(len(diff)), n_prior)
    sharpe_improved = _sharpe(te_e) > _sharpe(te_b)
    # both pre-registered conditions must hold; the z bar alone is not enough
    if v["verdict"] == "SUPPORTED" and not sharpe_improved:
        v = dict(v, verdict="NOT SIGNIFICANT",
                 reason=v["reason"] + "; TEST Sharpe did not improve")

    stats = {
        "test_days": int(len(diff)),
        "test_start": str(te_b.index[0].date()), "test_end": str(te_b.index[-1].date()),
        "mean_daily_diff": float(diff.mean()), "sd_daily_diff": float(diff.std()),
        "test_sharpe_base": _sharpe(te_b), "test_sharpe_excl": _sharpe(te_e),
        "test_maxdd_base": _maxdd(te_b), "test_maxdd_excl": _maxdd(te_e),
        "train_sharpe_base": _sharpe(tr_b), "train_sharpe_excl": _sharpe(tr_e),
        "full_sharpe_base": _sharpe(base), "full_sharpe_excl": _sharpe(excl),
    }
    J.record(NAME, HYPOTHESIS, stats, v,
             "Deployed long-only 1x config, monthly, 5bps. Verdict below SUPPORTED "
             "means crypto stays in the book.")

    print(f"\n  {NAME}  --  {v['verdict']}")
    print(f"  TEST {stats['test_start']}..{stats['test_end']} ({stats['test_days']} days)")
    print(f"  Sharpe base {stats['test_sharpe_base']:.2f}  ex-crypto {stats['test_sharpe_excl']:.2f}"
          f"  | MaxDD base {stats['test_maxdd_base']:.1%}  ex-crypto {stats['test_maxdd_excl']:.1%}")
    print(f"  mean daily diff {stats['mean_daily_diff']:+.6f}  z={v.get('z'):+.2f}"
          f"  required z>={v.get('required_z'):.2f}\n")
    return v


if __name__ == "__main__":
    run()
