#!/usr/bin/env python3
"""Research engine CLI.

  python3 run_research.py status    what is known, and the current evidence bar
  python3 run_research.py seed      load established findings into the journal
  python3 run_research.py monitor   is the live book inside its expected band?
  python3 run_research.py power     how many trades an edge would need to prove
"""
import sys, json
from research import journal as J, protocol as P, monitor as M, seed as S, cycle as CY

def cmd_status():
    s = J.summary(); n = s["tested"]
    print(f"\n  RESEARCH JOURNAL — {n} hypotheses tested")
    print("  " + "-"*62)
    for k, v in sorted(s["by_verdict"].items()): print(f"  {k:<18} {v}")
    print("  " + "-"*62)
    print("  SUPPORTED (in use):")
    for x in s["supported"]: print(f"    + {x}")
    print("  DEAD (never retest without new data):")
    for x in s["dead"]: print(f"    - {x}")
    print("  " + "-"*62)
    print(f"  next claim must clear z >= {P.required_z(n):.2f}  "
          f"(rises with every test — that is the point)\n")

def cmd_seed(): print(f"  seeded {S.run()} findings")

def cmd_monitor():
    from live import paper
    st = paper.load()
    if not st: print("  no live state"); return
    h = st.get("history", [])
    if len(h) < 2: print(f"  {len(h)} daily marks so far — need >= 20 to judge"); return
    days = len(h)
    live = h[-1]["equity_usd"]/h[0]["equity_usd"] - 1
    r = M.check(live, daily_mean=0.088/252, daily_sd=0.079/(252**0.5), days=days)
    print(f"\n  live {live*100:+.2f}% over {days} days")
    print(f"  expected band: {r['lo']*100:+.2f}% .. {r['hi']*100:+.2f}%")
    print(f"  STATUS: {r['status']} — {r['detail']}\n")

def cmd_power():
    n = J.n_tests()
    print(f"\n  trades needed to PROVE an edge, after {n} prior tests (z>={P.required_z(n):.2f}):")
    for eff, sd, label in [(0.07,1.42,"fib-sized edge (0.07R)"),
                           (0.20,1.42,"strong per-trade edge (0.20R)"),
                           (0.50,1.42,"huge per-trade edge (0.50R)")]:
        k = P.sample_size_needed(eff, sd, n)
        print(f"    {label:<32} {k:>8,} trades  = {k/10/12:>6,.0f} years at 10/month")
    print()

def cmd_cycle():
    """One autonomous research cycle: watch, re-verify, test, report."""
    import pandas as pd

    def retest_trend():
        """Re-verify the deployed trend edge on all data available today."""
        r = pd.read_csv("output/returns.csv", index_col=0, parse_dates=True).iloc[:, 0].dropna()
        return float(r.mean()), float(r.std()), int(len(r))

    def retest_trend_alpha():
        from research import factors
        r = pd.read_csv("output/returns.csv", index_col=0, parse_dates=True).iloc[:, 0].dropna()
        a = factors.alpha(r)
        return a["alpha_daily"], a["resid_sd"], a["n"]

    CY.run({"trend.multiscale": retest_trend,
            "trend.long_only": retest_trend,
            "trend.alpha_vs_ff3": retest_trend_alpha})

CMDS={"status":cmd_status,"seed":cmd_seed,"monitor":cmd_monitor,"power":cmd_power,"cycle":cmd_cycle}
if __name__=="__main__":
    c=sys.argv[1] if len(sys.argv)>1 else "status"
    if c not in CMDS: print(__doc__); sys.exit(1)
    CMDS[c]()
