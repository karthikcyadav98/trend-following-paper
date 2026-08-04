"""Load everything already established into the journal.

Knowledge only compounds if it persists. These are real results from this
project's own testing, recorded so no future run re-spends effort rediscovering
them -- and so the multiple-testing bar already reflects the searching done.
"""
from . import journal as J

FINDINGS = [
    ("fib.baseline", "Trend-based fib extension has an edge",
     {"mean": -0.073, "sd": 1.42, "n": 355}, "REJECTED",
     "355 trades, PF 0.88. 1/72 parameter configs profitable."),
    ("fib.vol_filter", "Filtering low-ATR markets adds edge",
     {"mean": 0.144, "sd": 1.5, "n": 54}, "NOT SIGNIFICANT",
     "Turned out to be 'don't trade 1h forex'; crypto identical with/without."),
    ("fib.trend_filter", "EMA-gap regime filter adds edge",
     {"mean": 0.096, "sd": 1.45, "n": 86}, "NOT SIGNIFICANT", "Unstable across thresholds."),
    ("fib.shallow_retrace", "Capping retracement at 50% adds edge",
     {"mean": 0.001, "sd": 1.4, "n": 114}, "REJECTED", "Zero effect out of sample."),
    ("fib.single_target", "Exiting all at T1 beats scaling to T2",
     {"mean": -0.141, "sd": 1.4, "n": 170}, "REJECTED", ""),
    ("fib.high_rr", "Requiring R:R >= 3.5 adds edge",
     {"mean": -0.103, "sd": 1.5, "n": 74}, "REJECTED", ""),
    ("fib.kitchen_sink", "Stacking every filter that helped on train",
     {"mean": 0.180, "sd": 1.8, "n": 21}, "NOT SIGNIFICANT",
     "Train +0.559R collapsed to +0.180 +/- 0.393. Textbook overfit."),
    ("fib.session_asia", "Asia-session entries outperform",
     {"mean": 0.147, "sd": 1.4, "n": 124}, "NOT SIGNIFICANT",
     "Split-half decayed +0.264 -> +0.029. Noise."),
    ("fib.forex_4h", "Coarser timeframe fixes the cost drag",
     {"mean": 0.006, "sd": 1.4, "n": 97}, "NOT SIGNIFICANT",
     "Real mechanism, but only moves it to breakeven; died at 16 pairs."),
    ("trend.multiscale", "Cross-asset time-series momentum has an edge",
     {"mean": 0.00045, "sd": 0.0079, "n": 5300}, "SUPPORTED",
     "Sharpe 0.93. All 24 configs positive, all 8 subperiods positive, "
     "beats 100% of 200 random-signal books."),
    ("trend.long_only", "Long-only unlevered beats long/short 3x risk-adjusted",
     {"mean": 0.00035, "sd": 0.0050, "n": 5300}, "SUPPORTED",
     "Sharpe 1.12 vs 0.92, MaxDD -10.5% vs -18.8%. Deployed."),
]


def run():
    have = {e["name"] for e in J.entries() if e.get("kind") == "result"}
    added = 0
    for name, hyp, stats, verdict, notes in FINDINGS:
        if name in have:
            continue
        J.record(name, hyp, stats, {"verdict": verdict, "seeded": True}, notes)
        added += 1
    return added
