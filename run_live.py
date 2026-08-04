#!/usr/bin/env python3
"""Live paper trading for the trend book.

  python3 run_live.py update    advance the Rs 100,000 paper portfolio
  python3 run_live.py report    print the current book
  python3 run_live.py serve     dashboard on http://127.0.0.1:8788
"""
import sys, datetime as dt
from live.universe import all_tickers
from live import paper

def cmd_update():
    print("\n  updating trend paper portfolio...")
    st = paper.update(all_tickers(), verbose=True)
    paper.save(st)

def cmd_report():
    st = paper.load()
    if not st:
        print("\n  no state yet -- run: python3 run_live.py update\n"); return
    f = lambda m: dt.datetime.fromtimestamp(m/1000).strftime("%Y-%m-%d %H:%M")
    pnl = st["equity_inr"] - st["start_inr"]
    print(f"\n  TREND PAPER BOOK  (started {f(st['started_at'])})")
    print("  " + "-"*58)
    print(f"  start          Rs {st['start_inr']:,.0f}")
    print(f"  equity         Rs {st['equity_inr']:,.0f}   (${st['equity_usd']:,.2f})")
    print(f"  P&L            Rs {pnl:+,.0f}  ({100*pnl/st['start_inr']:+.2f}%)")
    print(f"  USDINR         {st['usdinr']:.2f}  (start {st['usdinr_start']:.2f})")
    print(f"  gross exposure {st.get('gross',0):.2f}x | last rebalance {st.get('last_rebalance')}")
    print("  " + "-"*58)
    hv = st.get("holdings_value", {})
    for t, v in sorted(hv.items(), key=lambda x: -abs(x[1])):
        w = v/st["equity_usd"] if st["equity_usd"] else 0
        print(f"  {t:<9} ${v:>10,.0f}  {100*w:>5.1f}%   signal {st['signals'].get(t)}")
    print()

def cmd_serve():
    from live import server
    server.serve(int(sys.argv[2]) if len(sys.argv) > 2 else 8788)

CMDS = {"update": cmd_update, "report": cmd_report, "serve": cmd_serve}
if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "report"
    if c not in CMDS: print(__doc__); sys.exit(1)
    CMDS[c]()
