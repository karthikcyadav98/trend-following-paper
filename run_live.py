#!/usr/bin/env python3
"""Live paper trading for the trend book.

  python3 run_live.py update     advance the Rs 100,000 paper portfolio
  python3 run_live.py report     print the current book
  python3 run_live.py charges    refresh the charge/tax rate card
  python3 run_live.py withdraw   what a full cash-out would leave in hand
  python3 run_live.py serve      dashboard on http://127.0.0.1:8788
"""
import sys, datetime as dt
from live.universe import all_tickers
from live import paper

def cmd_update():
    print("\n  updating trend paper portfolio...")
    st = paper.update(all_tickers(), verbose=True)
    paper.save(st)
    from live import charges
    charges.write()

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

def cmd_charges():
    from live import charges
    print(f"  wrote {charges.write()}  (rates as of {charges.AS_OF})")


def cmd_withdraw():
    """Price a full liquidation: broker, FX, tax, and what actually lands."""
    from live import charges as C
    st = paper.load()
    if not st:
        print("\n  no state yet -- run: python3 run_live.py update\n"); return

    slab = float(sys.argv[2]) if len(sys.argv) > 2 else C.SLAB_DEFAULT
    px, hold = st.get("prices", {}), st.get("holdings", {})
    now = st.get("last_update") or 0

    gross = sum(u * px.get(t, 0) for t, u in hold.items())
    shares = sum(hold.values())
    sc = C.sell_costs(gross, shares)
    proceeds = gross - sc["total"] + st.get("cash_usd", 0)

    # Rule 115: cost in rupees at the buy-date rate, proceeds at today's rate.
    buy_rate, sell_rate = st.get("usdinr_start", 0), st.get("usdinr", 0)
    lt = stg = 0.0
    for ticker, lots in C.open_lots(st.get("trades", [])).items():
        for lot in lots:
            cost_inr = lot["units"] * lot["price"] * buy_rate
            val_inr = lot["units"] * px.get(ticker, 0) * sell_rate
            gain = val_inr - cost_inr
            if C.months_between(lot["ts"], now) >= C.LTCG_MONTHS:
                lt += gain
            else:
                stg += gain

    tax = C.capital_gains_tax(lt, stg, slab=slab)
    rep = C.repatriate(proceeds, sell_rate)
    inhand = rep["credited_inr"] - tax["total"]

    print(f"\n  FULL CASH-OUT  (rates as of {C.AS_OF}, slab {slab:.0%})")
    print("  " + "-" * 58)
    print(f"  market value          ${gross:>12,.2f}")
    print(f"  sell-side costs       ${-sc['total']:>12,.2f}   SEC + FINRA + brokerage")
    print(f"  cash already idle     ${st.get('cash_usd', 0):>12,.2f}")
    print(f"  repatriated           ${proceeds:>12,.2f}  @ {rep['tt_rate']:.2f} TT")
    print("  " + "-" * 58)
    print(f"  gross rupees          Rs {rep['gross_inr']:>11,.0f}")
    print(f"  FX spread lost        Rs {-rep['fx_spread_cost']:>11,.0f}   {C.FX_MARKUP_DEFAULT:.2%} off mid")
    print(f"  remittance + GST      Rs {-(rep['remit_fee'] + rep['remit_fee_gst'] + rep['conversion_gst']):>11,.0f}")
    print(f"  credited to bank      Rs {rep['credited_inr']:>11,.0f}")
    print("  " + "-" * 58)
    print(f"  short-term gain       Rs {stg:>11,.0f}   taxed at slab")
    print(f"  long-term gain        Rs {lt:>11,.0f}   taxed at {C.LTCG_RATE:.1%}")
    print(f"  tax + cess            Rs {-tax['total']:>11,.0f}")
    print("  " + "-" * 58)
    print(f"  IN HAND               Rs {inhand:>11,.0f}   "
          f"({100 * (inhand / st['start_inr'] - 1):+.2f}% on Rs {st['start_inr']:,.0f})")
    print(f"\n  {C.snapshot()['disclaimer']}\n")


CMDS = {"update": cmd_update, "report": cmd_report, "serve": cmd_serve,
        "charges": cmd_charges, "withdraw": cmd_withdraw}
if __name__ == "__main__":
    c = sys.argv[1] if len(sys.argv) > 1 else "report"
    if c not in CMDS: print(__doc__); sys.exit(1)
    CMDS[c]()
