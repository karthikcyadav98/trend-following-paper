"""The autonomous research cycle.

Run on a schedule, this is the part that makes the system grow. Each cycle does
four things, in this order, and never any others:

  1. WATCH    is each live book inside the distribution its backtest predicted?
              Divergence raises an alarm. It never triggers a parameter change --
              that rule is the whole reason this project is not a curve-fitting
              machine (see protocol.py).

  2. RE-VERIFY  re-test every SUPPORTED finding on all data available today,
              including the months that have printed since it was accepted. An
              edge that has decayed gets DEMOTED and flagged for removal from
              the live book. This is the self-fixing half: promotion is hard,
              but demotion is automatic.

  3. TEST     run the next un-tested hypothesis from the queue under the full
              protocol -- pre-registration, holdout, and the multiple-testing
              bar that has risen with every test ever run.

  4. REPORT   write the state of knowledge to disk for the dashboard.

What it deliberately cannot do: change a live parameter, re-test a dead idea to
"see if it works now", or lower the bar because nothing has passed lately.
"""

import json
import os
import time

from . import journal as J, monitor as M, protocol as P

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPORT = os.path.join(ROOT, "state", "research.json")

# Backtested daily stats of each deployed book, used to build the alarm band.
LIVE_BOOKS = {
    "trend-following": {"daily_mean": 0.088 / 252, "daily_sd": 0.079 / (252 ** 0.5),
                        "source": "live/paper.py"},
}

# Ideas waiting to be tested. Adding one costs something: it raises the bar for
# everything afterwards, so speculative entries are not free.
#
# Pruned 2026-08-05 (journalled, kind="prune" -- no bar cost, nothing was run):
#   nse.momentum.vol_scaled   duplicate of nse.momentum.volscale, already REJECTED
#   nse.momentum.12_1_vs_6_1  lookback variant of a dead parent strategy
QUEUE = [
    {"name": "trend.crypto_exclusion",
     "hypothesis": "Excluding BTC/ETH from the trend book improves risk-adjusted return",
     "criteria": "SUPPORTED if TEST Sharpe improves and z clears the bar"},
]


def watch(live_state_loader=None):
    """Step 1: alarm on live-vs-expected divergence."""
    out = []
    for name, spec in LIVE_BOOKS.items():
        try:
            from live import paper
            st = paper.load()
            hist = (st or {}).get("history", [])
            if len(hist) < 2:
                out.append({"book": name, "status": "TOO EARLY",
                            "detail": f"{len(hist)} daily marks; need >= 20"})
                continue
            days = len(hist)
            ret = hist[-1]["equity_usd"] / hist[0]["equity_usd"] - 1
            r = M.check(ret, spec["daily_mean"], spec["daily_sd"], days)
            out.append({"book": name, "live_return": ret, "days": days, **r})
        except Exception as e:
            out.append({"book": name, "status": "ERROR", "detail": str(e)})
    return out


def reverify(retest_fns):
    """Step 2: re-test SUPPORTED findings on today's data; demote decayed ones.

    `retest_fns` maps a finding name to a callable returning (mean, sd, n).
    Anything without a retest function is reported as unverifiable rather than
    silently assumed still true.
    """
    results = []
    supported = {e["name"]: e for e in J.entries()
                 if e.get("kind") == "result" and e["verdict"]["verdict"] == "SUPPORTED"}
    n_prior = J.n_tests()
    for name in supported:
        fn = retest_fns.get(name)
        if fn is None:
            results.append({"name": name, "status": "NOT RE-TESTABLE",
                            "detail": "no retest function registered"})
            continue
        try:
            mean, sd, n = fn()
        except Exception as e:
            results.append({"name": name, "status": "ERROR", "detail": str(e)})
            continue
        v = P.evaluate(mean, sd, n, n_prior)
        status = "HOLDS" if v["verdict"] == "SUPPORTED" else "DECAYED"
        results.append({"name": name, "status": status, "mean": mean,
                        "z": v["z"], "required_z": v["required_z"]})
        if status == "DECAYED":
            J.record(name + ".reverify",
                     f"Re-verification of {name} on data through today",
                     {"mean": mean, "sd": sd, "n": n}, v,
                     "AUTOMATIC DEMOTION: previously SUPPORTED, no longer clears the bar.")
    return results


def next_untested():
    """Step 3: the first queued hypothesis with no recorded result."""
    done = {e["name"] for e in J.entries() if e.get("kind") == "result"}
    for h in QUEUE:
        if h["name"] not in done:
            return h
    return None


def report(watch_out, reverify_out, queued):
    s = J.summary()
    rec = {
        "generated": int(time.time() * 1000),
        "journal": s,
        "required_z": P.required_z(s["tested"]),
        "watch": watch_out,
        "reverify": reverify_out,
        "next_hypothesis": queued,
        "queue_remaining": len([h for h in QUEUE
                                if h["name"] not in {e["name"] for e in J.entries()
                                                     if e.get("kind") == "result"}]),
        "rules": [
            "Live P&L can raise an alarm; it can never promote a change.",
            "The significance bar rises with every hypothesis ever tested.",
            "Dead ideas are never retested without genuinely new data.",
            "Promotion requires pre-registration, holdout and beating the null.",
            "Demotion is automatic when a supported finding stops clearing the bar.",
        ],
    }
    os.makedirs(os.path.dirname(REPORT), exist_ok=True)
    with open(REPORT, "w") as f:
        json.dump(rec, f, indent=2)
    return rec


def run(retest_fns=None, verbose=True):
    w = watch()
    rv = reverify(retest_fns or {})
    nxt = next_untested()
    rec = report(w, rv, nxt)
    if verbose:
        print(f"\n  RESEARCH CYCLE  —  {rec['journal']['tested']} hypotheses tested, "
              f"bar z >= {rec['required_z']:.2f}")
        print("  " + "-" * 64)
        for x in w:
            print(f"  WATCH     {x['book']:<18} {x['status']}  {x.get('detail', '')[:44]}")
        for x in rv:
            extra = "" if x["status"] in ("NOT RE-TESTABLE", "ERROR") else f"z={x.get('z', 0):+.2f}"
            print(f"  REVERIFY  {x['name']:<18} {x['status']}  {extra}")
        print(f"  NEXT      {nxt['name'] if nxt else '(queue empty)'}")
        print("  " + "-" * 64)
    return rec
