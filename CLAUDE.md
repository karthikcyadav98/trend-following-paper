# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python3 -m venv .venv && .venv/bin/pip install pandas numpy yfinance matplotlib

# Backtest (writes output/tearsheet.png, returns.csv, weights.csv)
.venv/bin/python run.py
.venv/bin/python run.py --robustness            # sweeps, subperiods, random-signal null
.venv/bin/python run.py --refresh               # re-download prices into data/
# flags: --signal {multiscale,tsmom,ma,breakout} --rebalance {D,W,M} --cost-bps --vol-target --start

# Live paper book (state/portfolio.json)
python3 run_live.py update|report|serve         # serve = dashboard on 127.0.0.1:8788

# Research governance engine (state/journal.jsonl, state/research.json)
python3 run_research.py status|seed|monitor|power|cycle

# One pre-registered hypothesis test
python3 -m research.crypto_excl
```

There is no test suite. The equivalent of "running the tests" is `run.py --robustness`
(24 config combinations, 8 subperiods, 200 random sign-flipped books) plus
`run_research.py cycle`, which re-verifies every SUPPORTED finding on today's data.

`live/` and `research/` need only `pandas` + `numpy` — keep it that way; both are
imported by GitHub Actions runners that deliberately do not install `yfinance`.

## Architecture

Four subsystems, one shared rule: **the deployed book must reuse the validated code,
never reimplement it.**

**`trend/` — the backtest.** `data.load_prices` caches to `data/<ticker>.csv` and snaps
crypto onto the exchange calendar (weekends would corrupt every `sqrt(252)`).
`strategy.py` produces signals and inverse-vol weights using only information at close
of `t`; it never lags. `backtest.run_backtest` owns the single `shift(1)` that turns
signals into realised returns — that line is the entire separation between a backtest
and a fantasy, so treat it as load-bearing. `robustness.py` exists to break the
strategy, not flatter it.

**`live/` — the Rs 100,000 paper book.** `paper.target_book` calls `trend.strategy`
directly. Its config is **not** the headline backtest: it is LONG-ONLY, gross capped at
1.0x, with the per-asset cap re-applied *after* vol targeting (Sharpe 1.12 vs 0.92,
MaxDD -10.5% vs -18.8%, and it needs no margin or shorting). `feed.py` talks to Yahoo's
JSON chart endpoint with stdlib only — the short user-agent string is deliberate, a full
Chrome UA gets 429ed. `universe.py` duplicates `trend.data.UNIVERSE` on purpose;
`check_matches_backtest()` is asserted in CI so the copy cannot drift.

**`research/` — the governance engine.** Read `research/protocol.py` before changing
anything here; it documents the failures this exists to prevent. The rules:
pre-register criteria before running, hold out data, pay a rising Bonferroni bar for
every look (`required_z(n_tests)` — currently z >= 3.07 after 22 tests), beat a random
null, journal forever, and **never let live P&L promote a change** (it can only raise an
alarm via `monitor.py`). Demotion, by contrast, is automatic: `cycle.reverify` demotes a
SUPPORTED finding the moment it stops clearing the bar. `journal.jsonl` is append-only.

**`nse/` — Indian cash-equity study (library, no CLI).** `bhav.py` builds a
survivorship-bias-free point-in-time panel from NSE bhavcopy; `study.py`, `size_check.py`,
`crash_fix.py`, `costs.py` test cross-sectional factors on it. Every hypothesis here was
REJECTED or NOT SIGNIFICANT — the 20bps STT round-trip and the inability to short in the
liquid band kill it. Do not resurrect these without genuinely new data.

## Adding a hypothesis

1. Append to `research/cycle.QUEUE` with `criteria` stated in advance. Adding an entry
   is not free: it raises the significance bar for everything after it.
2. Write a module modelled on `research/crypto_excl.py` — reproduce the *deployed*
   pipeline, split train/test by time, `J.preregister(...)` before computing anything,
   `J.record(...)` exactly once, and refuse to re-run if a result already exists.
3. Anything short of SUPPORTED changes nothing in the live book.

## State, CI, and data

- `state/` is committed (portfolio.json, journal.jsonl, research.json) — that is how the
  hosted book and the dashboard persist. `data/` and `cache/` are git-ignored.
- `.github/workflows/paper.yml` marks the book twice each weekday, rebalances monthly,
  commits `state/`, and publishes `web/index.html` + `state/*.json` to GitHub Pages.
- `.github/workflows/research.yml` runs the weekly cycle. It can demote a finding and
  raise alarms; it cannot promote a change or touch a live parameter.
- Bot commits (`trend: <ts>`, `research: cycle <date>`) are machine-generated; don't
  hand-edit `state/` to "fix" them.

## Honesty constraints

The README's "Read this before believing any of it" section is the project's tone and
its standard. Sharpe is ~0.86, 40% of months lose, the longest drawdown ran 784 days,
and the result is in-sample. When reporting numbers, keep the caveats attached — the
codebase treats a flattering number without its failure modes as a bug.
