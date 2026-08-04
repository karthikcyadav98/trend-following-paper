"""Realistic Indian equity transaction costs -- and the shorting constraint.

COSTS (delivery, discount broker, per leg unless noted)
    brokerage          0.03% capped at Rs 20/order (Zerodha/Groww style)
    STT                0.10% on buy AND 0.10% on sell (delivery)
    exchange txn       0.00297% (NSE cash)
    SEBI turnover      0.0001%
    stamp duty         0.015% on buy only
    GST 18%            on brokerage + exchange + SEBI
    impact             assumed separately; scales with how much of the day's
                       turnover the order represents

STT dominates: 20bps of round-trip cost before anything else. That alone is
most of the 35bps/side used in the study.

THE HARDER CONSTRAINT: YOU CANNOT SHORT
    Indian cash-market delivery has no overnight short. A short position must be
    carried in single-stock futures, and only ~180 names have F&O -- all of them
    highly liquid. The momentum spread was measured to be FLAT in exactly that
    liquid band (-0.03%/mo in the most-liquid tercile, +0.38%/mo top-200).

    So the long-short book is not merely expensive here, it is unimplementable:
    the leg you cannot trade is the leg that carries the return. What remains is
    long-only, whose honest benchmark is the equal-weight universe, not zero.
"""

BROKERAGE_PCT = 0.0003
BROKERAGE_CAP = 20.0
STT_BUY = 0.0010
STT_SELL = 0.0010
EXCHANGE = 0.0000297
SEBI = 0.000001
STAMP_BUY = 0.00015
GST = 0.18


def one_leg_bps(notional, side, impact_bps=0.0):
    """All-in cost of one leg, in bps of notional."""
    if notional <= 0:
        return 0.0
    brokerage = min(notional * BROKERAGE_PCT, BROKERAGE_CAP)
    exch = notional * EXCHANGE
    sebi = notional * SEBI
    gst = (brokerage + exch + sebi) * GST
    stt = notional * (STT_BUY if side == "buy" else STT_SELL)
    stamp = notional * STAMP_BUY if side == "buy" else 0.0
    total = brokerage + exch + sebi + gst + stt + stamp
    return (total / notional) * 10000.0 + impact_bps


def round_trip_bps(notional, impact_bps=0.0):
    return one_leg_bps(notional, "buy", impact_bps) + one_leg_bps(notional, "sell", impact_bps)


def impact_bps_for(order_value, daily_turnover, k=10.0):
    """Square-root impact: k * sqrt(participation), in bps.

    At Rs 1 lakh spread over ~50 names the participation rate is ~1e-5, so
    impact is a rounding error. This matters for size, not for this account.
    """
    if daily_turnover <= 0:
        return 50.0
    part = order_value / daily_turnover
    return k * (part ** 0.5) * 10000.0 / 100.0
