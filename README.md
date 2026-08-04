# Cross-asset trend following — backtest

Time-series momentum across equities, rates, commodities, FX and crypto, with
inverse-volatility sizing and a portfolio volatility target.

```bash
python3 -m venv .venv && .venv/bin/pip install pandas numpy yfinance matplotlib
.venv/bin/python run.py                # baseline + tearsheet
.venv/bin/python run.py --robustness   # sweeps, subperiods, random-signal test
.venv/bin/python run.py --refresh      # re-download prices
```

Options: `--signal {multiscale,tsmom,ma,breakout}`, `--rebalance {D,W,M}`,
`--cost-bps`, `--vol-target`, `--start`.

## Layout

| File | Role |
| --- | --- |
| `trend/data.py` | Download + CSV cache, exchange-calendar alignment |
| `trend/strategy.py` | Signals and volatility sizing |
| `trend/backtest.py` | Engine and performance statistics |
| `trend/robustness.py` | Parameter sweeps, subperiods, random-signal test |
| `trend/plots.py` | Four-panel tearsheet |
| `run.py` | CLI |

Outputs land in `output/` (`tearsheet.png`, `returns.csv`, `weights.csv`).

## How it works

1. **Signal** — default `multiscale` averages the sign of 3/6/12-month returns.
   Averaging horizons avoids picking the one lookback that happened to
   backtest best.
2. **Sizing** — each position scaled by `20% / trailing_vol` (60-day EWMA), so
   crude oil and 7-10y Treasuries contribute comparable risk. Capped at 25%
   per asset and 3x gross.
3. **Portfolio vol target** — book rescaled so trailing realised vol tracks
   12%.
4. **Execution** — signals computed at the close of day *t*, earn the return of
   *t+1*. That single `shift(1)` in `run_backtest` is what keeps this honest.
5. **Costs** — 5bps per unit of turnover by default.

Assets enter the book as their history begins (BTC in 2014, ETH in 2017) rather
than being backfilled.

## Results (2005-05 → 2026-07, 5bps, monthly rebalance)

| | CAGR | Vol | Sharpe | MaxDD | Calmar | Mth win% |
| --- | --- | --- | --- | --- | --- | --- |
| **Trend** | 10.8% | 12.5% | **0.86** | **-18.9%** | 0.57 | 59.6% |
| SPY | 11.2% | 19.0% | 0.59 | -55.2% | 0.20 | 67.1% |
| 60/40 | 8.5% | 11.0% | 0.78 | -31.4% | 0.27 | 68.6% |

Robustness: Sharpe stays in 0.47–0.89 across all 24 signal/rebalance/cost
combinations; positive in all 8 three-year subperiods; beats 100% of 200
random sign-flipped books with identical sizing and costs (real 0.86 vs random
mean -0.18).

## Read this before believing any of it

- **The Sharpe is ~0.86, not 3.** This is a real but modest edge.
- **Lower return than SPY.** The case for it is the drawdown: -19% vs -55%. It
  is a diversifier, not a replacement for equity beta.
- **Longest drawdown was 784 days.** Over two years underwater. 2023 lost 8.6%,
  2012 lost 9.4%. Anyone who abandons the rules during those stretches gets the
  losses without the recovery.
- **40% of months lose money.** There is no monthly-profit version of this.
- **It is in-sample.** The universe, the date range and the parameters were all
  chosen with hindsight. The robustness checks reduce the chance that this is
  pure curve-fitting; they do not eliminate it. Expect live results meaningfully
  worse than backtest.
- **ETFs are a proxy.** Real managed futures run futures — cheaper, deeper, and
  with different financing. Costs here are a rough 5bps assumption, not modelled
  slippage.
- **2008 and 2022 carry the record.** Trend earns its keep in sustained
  selloffs. Strip those two years and the edge over 60/40 largely disappears.
