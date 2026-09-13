"""What it actually costs to run and cash out this book from India.

WHAT THIS IS NOT
----------------
This is not the book's own cost model. `live/paper.py` charges a flat 5bps per
side, and that number is what the validated backtest used. Changing it would
invalidate the weekly re-verification in `research/cycle.py` and would be a live
parameter change made without pre-registration -- exactly what
`research/protocol.py` forbids. So this module never touches the simulation.

It is an OVERLAY. The book is denominated in USD and funded in rupees, which
means the number on the dashboard is a *gross* number: it has not paid a broker,
a bank, or the Income Tax Department. This module prices that gap so the
dashboard can show what would actually land in a bank account.

THE ROUTE BEING PRICED
----------------------
An Indian resident individual buying US-listed ETFs through the Liberalised
Remittance Scheme (LRS), holding them at a US broker, and repatriating the
proceeds to an Indian savings account. That is the route this book's universe
implies -- SPY and IEF are not available on an Indian exchange.

EVERY RATE IS A DATED CONSTANT
------------------------------
Tax and fee rates move. Each constant below carries what it is and when it was
current. They are exported to `state/charges.json` so the dashboard shows the
same numbers this module computes, rather than a second copy that can drift
(the same reason `live/universe.py` has `check_matches_backtest`).

NOT TAX ADVICE. This is an estimate built from published rates, and it cannot
know an individual's other income, prior losses, carried-forward capital losses,
DTAA position, or residency status -- all of which change the answer. Anyone
acting on a real repatriation should have a qualified professional confirm it.
"""

import json
import os

STATE_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
CHARGES_PATH = os.path.join(STATE_DIR, "charges.json")

AS_OF = "2026-08-21"

# ---------------------------------------------------------------------------
# US side -- what the broker and the exchanges take
# ---------------------------------------------------------------------------
# Retail LRS platforms (Vested, INDmoney, IBKR Lite) run $0 commission on US
# ETFs; IBKR Pro and some tiers charge per-share. Default to zero and let the
# dashboard raise it, rather than quietly assuming a fee nobody pays.
BROKERAGE_PER_ORDER_USD = 0.00
BROKERAGE_PER_SHARE_USD = 0.00

# SEC Section 31 fee -- charged on SELLS only, never on buys. The rate is reset
# by the SEC each fiscal year; FY2025 was $27.80 per $1,000,000 of proceeds.
SEC_FEE_RATE = 27.80 / 1_000_000

# FINRA Trading Activity Fee -- sells only, per share, capped per order.
FINRA_TAF_PER_SHARE = 0.000166
FINRA_TAF_CAP_USD = 8.30

# ---------------------------------------------------------------------------
# FX -- the spread is the real cost, not the wire fee
# ---------------------------------------------------------------------------
# Banks and LRS platforms quote a TT rate a margin away from mid-market. 0.5% is
# a good platform, 1.5%-2% is a bad bank. This dominates the wire fee at this
# account size and is the number most people never look at.
FX_MARKUP_DEFAULT = 0.0075          # 75bps off mid-market on the way back
INWARD_REMIT_FEE_INR = 500.0        # correspondent + receiving bank, typical
GST_RATE = 0.18                     # on fee-type services

# GST on foreign-exchange conversion is charged on a notional "taxable value"
# that steps with the amount (Rule 32(2)(b), CGST Rules).
def fx_taxable_value(amount_inr):
    """Taxable value of the conversion service, in rupees."""
    if amount_inr <= 100_000:
        return max(250.0, 0.01 * amount_inr)
    if amount_inr <= 1_000_000:
        return 1_000.0 + 0.005 * (amount_inr - 100_000)
    return min(60_000.0, 5_500.0 + 0.001 * (amount_inr - 1_000_000))


def fx_conversion_gst(amount_inr):
    return GST_RATE * fx_taxable_value(amount_inr)


# ---------------------------------------------------------------------------
# Indian capital gains on foreign assets
# ---------------------------------------------------------------------------
# US-listed ETFs are not "listed securities" for Indian tax purposes, so they
# carry the 24-month long-term threshold, not 12.
LTCG_MONTHS = 24
LTCG_RATE = 0.125                   # 12.5%, no indexation (Finance Act 2024)
CESS_RATE = 0.04                    # health & education cess, on tax + surcharge

# Short-term gains on foreign assets are taxed at the slab rate -- there is no
# concessional 15%/20% rate for them, which is the detail people most often get
# wrong when they assume US ETFs work like Indian equity.
SLAB_RATES = [0.0, 0.05, 0.10, 0.15, 0.20, 0.30]
SLAB_DEFAULT = 0.30

# Surcharge on capital gains is capped at 15% even in the higher income bands.
SURCHARGE_BANDS = [(0.0, "below Rs 50L total income"),
                   (0.10, "Rs 50L - 1Cr"),
                   (0.15, "above Rs 1Cr (capital gains surcharge is capped here)")]

# TCS on the OUTWARD remittance, not on the way back. Creditable against the
# year's tax liability, so it is a cash-flow cost, not a real one.
TCS_RATE = 0.20
TCS_THRESHOLD_INR = 1_000_000       # per financial year, per PAN

# Dividends are withheld at 25% in the US under the India-US DTAA and then taxed
# in India at slab with a foreign tax credit. The paper book does not model
# dividends at all -- see `dividend_note` below. Stating the gap beats inventing
# a number for it.
US_DIVIDEND_WITHHOLDING = 0.25


# ---------------------------------------------------------------------------
# Can an Indian resident actually buy these?
# ---------------------------------------------------------------------------
# Three different answers, and the book contains all three. Broker catalogues
# change, so treat "limited" as "check your platform", not as settled fact --
# but the two structural reasons below do not change:
#
#   * A commodity POOL (not a 1940-Act fund) issues a Schedule K-1 instead of a
#     1099. Vested and INDmoney generally do not list them; IBKR does.
#   * LRS may not be remitted to buy crypto. That is an RBI restriction on the
#     rail, not a broker preference, so the crypto sleeve has to be bought in
#     rupees on an Indian exchange and is taxed under s.115BBH instead.
INDIA_ACCESS = {
    "SPY":  ("ok", "1940-Act ETF, on every LRS platform"),
    "QQQ":  ("ok", "1940-Act ETF, on every LRS platform"),
    "EFA":  ("ok", "1940-Act ETF"),
    "EEM":  ("ok", "1940-Act ETF"),
    "TLT":  ("ok", "1940-Act ETF"),
    "IEF":  ("ok", "1940-Act ETF"),
    "GLD":  ("ok", "grantor trust; no US tax for a non-resident alien on gains"),
    "SLV":  ("ok", "grantor trust"),
    "FXE":  ("ok", "CurrencyShares grantor trust; thinner catalogues may omit it"),
    "FXY":  ("ok", "CurrencyShares grantor trust; thinner catalogues may omit it"),
    "DBC":  ("limited", "commodity pool, issues a K-1 -- often unavailable on Indian LRS platforms"),
    "USO":  ("limited", "commodity pool, issues a K-1 -- often unavailable on Indian LRS platforms"),
    "UUP":  ("limited", "commodity pool, issues a K-1 -- often unavailable on Indian LRS platforms"),
    "BTC-USD": ("separate", "LRS cannot be remitted to buy crypto; INR rail only, 30% + 1% TDS"),
    "ETH-USD": ("separate", "LRS cannot be remitted to buy crypto; INR rail only, 30% + 1% TDS"),
}

ACCESS_LABEL = {
    "ok": "Available via LRS",
    "limited": "K-1 commodity pool -- check your platform",
    "separate": "Not via LRS -- Indian exchange, different tax",
}


def sell_costs(notional_usd, shares, per_order=BROKERAGE_PER_ORDER_USD,
               per_share=BROKERAGE_PER_SHARE_USD):
    """US-side cost of liquidating one position. Sells only."""
    brokerage = per_order + per_share * shares
    sec = notional_usd * SEC_FEE_RATE
    taf = min(FINRA_TAF_CAP_USD, shares * FINRA_TAF_PER_SHARE)
    return {"brokerage": brokerage, "sec_fee": sec, "finra_taf": taf,
            "total": brokerage + sec + taf}


def open_lots(trades):
    """FIFO-match fills and return the lots still on the book.

    Matters for tax: the holding period runs per lot, so a position built in two
    rebalances can be part short-term and part long-term. Netting it into one
    average would quietly misstate the bill.
    """
    open_by = {}
    for t in sorted(trades or [], key=lambda x: x["ts"]):
        k = t["ticker"]
        lots = open_by.setdefault(k, [])
        if t["side"] == "buy":
            lots.append({"ts": t["ts"], "units": t["units"], "price": t["price"]})
        else:
            rem = t["units"]
            while rem > 1e-12 and lots:
                lot = lots[0]
                used = min(rem, lot["units"])
                lot["units"] -= used
                rem -= used
                if lot["units"] <= 1e-12:
                    lots.pop(0)
    return {k: v for k, v in open_by.items() if v}


def months_between(start_ms, end_ms):
    """Whole months between two epoch-millisecond stamps."""
    return (end_ms - start_ms) / (1000 * 60 * 60 * 24 * 30.4375)


def capital_gains_tax(ltcg_inr, stcg_inr, slab=SLAB_DEFAULT, surcharge=0.0):
    """Tax on realised gains, in rupees.

    Gains are computed in RUPEES, not dollars: Rule 115 converts the cost at the
    TT buy rate on the acquisition date and the proceeds at the rate on the sale
    date, so rupee depreciation is itself taxable gain. A book that made nothing
    in dollars can still owe tax.
    """
    ltcg_tax = max(0.0, ltcg_inr) * LTCG_RATE
    stcg_tax = max(0.0, stcg_inr) * slab
    base = ltcg_tax + stcg_tax
    sur = base * surcharge
    cess = (base + sur) * CESS_RATE
    return {"ltcg_gain": ltcg_inr, "stcg_gain": stcg_inr,
            "ltcg_tax": ltcg_tax, "stcg_tax": stcg_tax,
            "surcharge": sur, "cess": cess, "total": base + sur + cess,
            "slab": slab, "surcharge_rate": surcharge}


def repatriate(usd, mid_rate, markup=FX_MARKUP_DEFAULT,
               remit_fee_inr=INWARD_REMIT_FEE_INR):
    """Convert USD back to rupees and land it in a bank account."""
    tt_rate = mid_rate * (1 - markup)
    gross_inr = usd * tt_rate
    spread_cost = usd * mid_rate - gross_inr
    fee = remit_fee_inr
    fee_gst = fee * GST_RATE
    conv_gst = fx_conversion_gst(gross_inr)
    credited = gross_inr - fee - fee_gst - conv_gst
    return {"usd": usd, "mid_rate": mid_rate, "tt_rate": tt_rate,
            "gross_inr": gross_inr, "fx_spread_cost": spread_cost,
            "remit_fee": fee, "remit_fee_gst": fee_gst,
            "conversion_gst": conv_gst, "credited_inr": credited}


def tcs_on_remittance(amount_inr, sent_this_fy_inr=0.0):
    """TCS due on money sent OUT under LRS. Zero below the annual threshold."""
    over = max(0.0, (sent_this_fy_inr + amount_inr) - TCS_THRESHOLD_INR)
    charged = min(over, amount_inr)
    return {"rate": TCS_RATE, "threshold": TCS_THRESHOLD_INR,
            "taxable_amount": charged, "tcs": charged * TCS_RATE,
            "creditable": True}


def snapshot():
    """The rate card, for the dashboard. One source of truth, exported."""
    return {
        "as_of": AS_OF,
        "us": {
            "brokerage_per_order_usd": BROKERAGE_PER_ORDER_USD,
            "brokerage_per_share_usd": BROKERAGE_PER_SHARE_USD,
            "sec_fee_rate": SEC_FEE_RATE,
            "sec_fee_note": "SEC Section 31, sells only, $27.80 per $1M (FY2025 rate)",
            "finra_taf_per_share": FINRA_TAF_PER_SHARE,
            "finra_taf_cap_usd": FINRA_TAF_CAP_USD,
            "dividend_withholding": US_DIVIDEND_WITHHOLDING,
        },
        "fx": {
            "markup_default": FX_MARKUP_DEFAULT,
            "inward_remit_fee_inr": INWARD_REMIT_FEE_INR,
            "gst_rate": GST_RATE,
            "gst_slabs": "1% up to Rs 1L (min Rs 250); Rs 1,000 + 0.5% to Rs 10L; "
                         "Rs 5,500 + 0.1% above, capped Rs 60,000",
        },
        "india": {
            "ltcg_months": LTCG_MONTHS,
            "ltcg_rate": LTCG_RATE,
            "ltcg_note": "Foreign ETFs are unlisted securities for Indian tax: "
                         "24-month threshold, 12.5% without indexation",
            "stcg_note": "Short-term gains on foreign assets are taxed at slab, "
                         "not at the 15%/20% rates that apply to Indian equity",
            "slab_rates": SLAB_RATES,
            "slab_default": SLAB_DEFAULT,
            "cess_rate": CESS_RATE,
            "surcharge_bands": [{"rate": r, "label": l} for r, l in SURCHARGE_BANDS],
            "tcs_rate": TCS_RATE,
            "tcs_threshold_inr": TCS_THRESHOLD_INR,
            "tcs_note": "Charged on money sent OUT under LRS above Rs 10L per FY, "
                        "and creditable against the year's tax -- a cash-flow cost",
            "rule_115": "Capital gains on foreign assets are computed in rupees: "
                        "cost at the rate on the buy date, proceeds at the rate on "
                        "the sell date, so rupee depreciation is taxable gain",
        },
        "india_access": {k: {"status": v[0], "note": v[1]} for k, v in INDIA_ACCESS.items()},
        "access_label": ACCESS_LABEL,
        "price_basis": "Both the backtest and the live feed use ADJUSTED closes, so ETF "
                       "expense ratios and reinvested dividends are already inside the "
                       "return series. Nothing extra needs deducting for either.",
        "book_cost_model": {
            "cost_bps": 5.0,
            "note": "What the simulation itself charges, per side, per unit of "
                    "turnover. Left untouched on purpose: it is the number the "
                    "validated backtest used.",
        },
        "dividend_note": "The paper book models price returns only. A real holder "
                         "would receive ETF distributions, lose 25% to US "
                         "withholding, and pay Indian slab tax with a foreign tax "
                         "credit. Neither the income nor the tax is in these figures.",
        "disclaimer": "Estimate from published rates. It cannot know other income, "
                      "carried-forward losses, or residency position. Not tax advice.",
    }


def write(path=CHARGES_PATH):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(snapshot(), f, indent=2)
    os.replace(tmp, path)
    return path


if __name__ == "__main__":
    print(f"  wrote {write()}")
