"""Live paper portfolio for the trend book. Starts at Rs 100,000.

Deliberately reuses `trend.strategy` rather than reimplementing the maths, so
the hosted book and the validated backtest cannot drift apart. The only things
added here are the parts a backtest does not need: persistent holdings, real
calendar rebalancing, and rupee accounting.

Configuration is LONG-ONLY with gross capped at 1.0x. That is not the headline
backtest -- it is the deployable one. Measured over 2005-2026:

    long/short, 3x cap   CAGR 11.4%  Sharpe 0.92  MaxDD -18.8%
    long-only, 1x cap    CAGR  8.8%  Sharpe 1.12  MaxDD -10.5%

Lower return, materially better risk-adjusted return and half the drawdown --
and it needs no margin account and no ability to short, which is what an LRS
investor actually has.
"""

import json
import os
import time

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
STATE_PATH = os.path.join(STATE_DIR, "portfolio.json")

START_INR = 100000.0
MAX_WEIGHT = 0.25
MAX_GROSS = 1.0        # no leverage
LONG_ONLY = True
COST_BPS = 5.0         # per unit of turnover, each way


def new_state(usdinr, capital_inr=START_INR):
    return {
        "start_inr": capital_inr,
        "usdinr_start": usdinr,
        "start_usd": capital_inr / usdinr,
        "cash_usd": capital_inr / usdinr,
        "holdings": {},            # ticker -> units
        "started_at": int(time.time() * 1000),
        "last_update": None,
        "last_rebalance": None,
        "history": [],
        "trades": [],
        "weights": {},
        "signals": {},
        "errors": [],
    }


def load():
    if os.path.exists(STATE_PATH):
        with open(STATE_PATH) as f:
            return json.load(f)
    return None


def save(state):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE_PATH + ".tmp"
    with open(tmp, "w") as f:
        json.dump(state, f, indent=2)
    os.replace(tmp, STATE_PATH)


def target_book(prices):
    """Target weights from the SAME functions the backtest validated."""
    import numpy as np
    from trend import strategy as st

    returns = st.daily_returns(prices)
    sig = st.signal_multiscale(prices)
    if LONG_ONLY:
        sig = sig.clip(lower=0)
    vol = st.ex_ante_volatility(returns, halflife=60)
    w = st.target_weights(sig, vol, asset_vol_target=0.20,
                          max_leverage=MAX_GROSS, max_weight=MAX_WEIGHT)
    w = st.apply_portfolio_vol_target(w, returns, portfolio_vol_target=0.12, halflife=60)
    if LONG_ONLY:
        w = w.clip(lower=0)
    # Re-apply the per-asset cap AFTER vol targeting. The backtest clips before
    # it, so the scale-up can push one asset to 47% of the book; re-clipping
    # holds it at 25% for statistically identical returns (Sharpe 1.10 vs 1.12,
    # CAGR 9.0% vs 8.8%). Cheap concentration insurance.
    w = w.clip(upper=MAX_WEIGHT)
    gross = w.abs().sum(axis=1)
    over = gross > MAX_GROSS
    if over.any():
        w.loc[over] = w.loc[over].div(gross[over] / MAX_GROSS, axis=0)
    latest = w.iloc[-1].fillna(0.0)
    return latest, sig.iloc[-1], vol.iloc[-1], returns


def mark(state, px):
    """Portfolio value in USD at the given prices."""
    v = state["cash_usd"]
    for t, u in state["holdings"].items():
        if t in px:
            v += u * px[t]
    return v


def rebalance(state, weights, px, equity):
    """Trade the book to target. Returns the fills."""
    fills = []
    for t, wt in weights.items():
        if t not in px or px[t] <= 0:
            continue
        want_units = (equity * float(wt)) / px[t]
        have = state["holdings"].get(t, 0.0)
        delta = want_units - have
        if abs(delta * px[t]) < equity * 0.005:     # ignore <0.5% nudges
            continue
        notional = delta * px[t]
        cost = abs(notional) * (COST_BPS / 10000.0)
        state["cash_usd"] -= notional + cost
        state["holdings"][t] = have + delta
        if abs(state["holdings"][t] * px[t]) < 1e-6:
            state["holdings"].pop(t, None)
        fills.append({
            "ts": int(time.time() * 1000),
            "ticker": t, "side": "buy" if delta > 0 else "sell",
            "units": abs(delta), "price": px[t],
            "notional": abs(notional), "cost": cost,
            "target_weight": float(wt),
        })
    return fills


def is_rebalance_day(state, today):
    """Monthly, matching the backtest's 'M' schedule."""
    last = state.get("last_rebalance")
    if not last:
        return True
    return today[:7] != last[:7]      # a new calendar month


def update(tickers, verbose=True):
    from . import feed

    prices, errs = feed.frame(tickers, rng="5y")
    rate = feed.usdinr()
    state = load() or new_state(rate)
    state["errors"] = errs

    px = {c: float(prices[c].iloc[-1]) for c in prices.columns}
    today = str(prices.index[-1].date())

    weights, sig, vol, _ = target_book(prices)
    equity = mark(state, px)

    fills = []
    if is_rebalance_day(state, today):
        fills = rebalance(state, weights, px, equity)
        state["last_rebalance"] = today
        state["trades"] = (state["trades"] + fills)[-400:]

    equity = mark(state, px)
    state["equity_usd"] = equity
    state["usdinr"] = rate
    state["equity_inr"] = equity * rate
    state["last_update"] = int(time.time() * 1000)
    state["last_bar"] = today
    state["prices"] = px
    state["weights"] = {t: float(weights.get(t, 0.0)) for t in prices.columns}
    state["signals"] = {t: (None if sig.get(t) != sig.get(t) else float(sig.get(t, 0)))
                        for t in prices.columns}
    state["vol"] = {t: (None if vol.get(t) != vol.get(t) else float(vol.get(t, 0)))
                    for t in prices.columns}
    state["holdings_value"] = {t: u * px.get(t, 0) for t, u in state["holdings"].items()}
    state["gross"] = sum(abs(v) for v in state["holdings_value"].values()) / equity if equity else 0

    hist = state["history"]
    if not hist or hist[-1]["date"] != today:
        hist.append({"date": today, "equity_usd": equity, "equity_inr": equity * rate})
    else:
        hist[-1] = {"date": today, "equity_usd": equity, "equity_inr": equity * rate}
    state["history"] = hist[-1500:]

    if verbose:
        print(f"  bar {today} | USDINR {rate:.2f}")
        print(f"  equity ${equity:,.2f}  =  Rs {equity * rate:,.0f}  "
              f"({100 * (equity * rate / state['start_inr'] - 1):+.2f}%)")
        print(f"  gross {state['gross']:.2f}x | holdings {len(state['holdings'])} | fills this run {len(fills)}")
        for f in fills:
            print(f"    {f['side'].upper():<4} {f['ticker']:<8} {f['units']:.4f} @ {f['price']:.2f}"
                  f"  (${f['notional']:,.0f}, target {100 * f['target_weight']:.1f}%)")
        if errs:
            print("  ! feed issues:", "; ".join(errs[:3]))
    return state
