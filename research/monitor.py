"""Is the live book behaving like the backtest, or has something broken?

Live results are used for ONE thing: raising an alarm. They never promote a
parameter change -- that is the rule in protocol.py. What they can legitimately
tell you is whether reality has left the distribution the backtest predicted,
which is a data/regime/implementation problem, not a tuning opportunity.
"""

import math


def expected_band(daily_mean, daily_sd, days, z=2.0):
    """Where cumulative return should sit if nothing is broken."""
    mu = daily_mean * days
    sd = daily_sd * math.sqrt(days)
    return {"expected": mu, "lo": mu - z * sd, "hi": mu + z * sd, "sd": sd}


def check(live_return, daily_mean, daily_sd, days, z=2.0):
    b = expected_band(daily_mean, daily_sd, days, z)
    if days < 20:
        return {"status": "TOO EARLY", "detail": f"{days} days live; need >= 20 to say anything", **b}
    if live_return < b["lo"]:
        return {"status": "BELOW BAND",
                "detail": "worse than the backtest's 95% band -- investigate data, costs or execution, "
                          "do NOT retune parameters", **b}
    if live_return > b["hi"]:
        return {"status": "ABOVE BAND",
                "detail": "better than expected; treat as luck, not skill, until it persists", **b}
    return {"status": "NORMAL", "detail": "live is inside the predicted distribution", **b}
