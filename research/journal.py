"""Append-only record of every hypothesis ever tested.

This is the part that actually compounds. A trading system does not get smarter
by tuning; it gets smarter by permanently knowing which ideas are dead, and by
making each new claim clear a higher bar than the last.

The journal is append-only on purpose: rewriting history is how a research log
turns back into a marketing document.
"""

import json
import os
import time

DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "state")
PATH = os.path.join(DIR, "journal.jsonl")


def entries():
    if not os.path.exists(PATH):
        return []
    out = []
    with open(PATH) as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line))
                except ValueError:
                    pass
    return out


def n_tests():
    """How many hypotheses have been tested -- the search cost paid so far."""
    return sum(1 for e in entries() if e.get("kind") == "result")


def already_tested(name):
    return {e["name"] for e in entries() if e.get("kind") == "result" and e.get("name") == name}


def append(rec):
    os.makedirs(DIR, exist_ok=True)
    rec = dict(rec, ts=int(time.time() * 1000))
    with open(PATH, "a") as f:
        f.write(json.dumps(rec) + "\n")
    return rec


def preregister(name, hypothesis, criteria):
    """Record intent BEFORE the test runs. Timestamps prove it came first."""
    return append({"kind": "prereg", "name": name,
                   "hypothesis": hypothesis, "criteria": criteria})


def record(name, hypothesis, stats, verdict, notes=""):
    return append({"kind": "result", "name": name, "hypothesis": hypothesis,
                   "stats": stats, "verdict": verdict, "notes": notes})


def summary():
    res = [e for e in entries() if e.get("kind") == "result"]
    by = {}
    for e in res:
        by[e["verdict"]["verdict"]] = by.get(e["verdict"]["verdict"], 0) + 1
    return {"tested": len(res), "by_verdict": by,
            "supported": [e["name"] for e in res if e["verdict"]["verdict"] == "SUPPORTED"],
            "dead": [e["name"] for e in res if e["verdict"]["verdict"] in ("REJECTED", "NOT SIGNIFICANT")]}
