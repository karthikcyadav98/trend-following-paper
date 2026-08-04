"""Price data download and on-disk caching."""

from __future__ import annotations

import time
from pathlib import Path

import pandas as pd
import yfinance as yf

CACHE_DIR = Path(__file__).resolve().parent.parent / "data"

# Diversified cross-asset universe. Trend following needs breadth across
# asset classes -- a trend book of only equities is just a beta bet.
UNIVERSE: dict[str, list[str]] = {
    "equity": ["SPY", "QQQ", "EFA", "EEM"],
    "rates": ["TLT", "IEF"],
    "commodity": ["GLD", "SLV", "DBC", "USO"],
    "fx": ["UUP", "FXE", "FXY"],
    "crypto": ["BTC-USD", "ETH-USD"],
}

BENCHMARK = "SPY"


def all_tickers(universe: dict[str, list[str]] | None = None) -> list[str]:
    universe = universe or UNIVERSE
    return [t for group in universe.values() for t in group]


def sector_of(ticker: str, universe: dict[str, list[str]] | None = None) -> str:
    universe = universe or UNIVERSE
    for sector, tickers in universe.items():
        if ticker in tickers:
            return sector
    return "other"


def _cache_path(ticker: str) -> Path:
    return CACHE_DIR / f"{ticker.replace('/', '_')}.csv"


def _download_one(ticker: str, start: str, retries: int = 3) -> pd.Series | None:
    """Download adjusted close for one ticker, with retries."""
    for attempt in range(retries):
        try:
            df = yf.download(
                ticker,
                start=start,
                auto_adjust=True,
                progress=False,
                threads=False,
            )
            if df is None or df.empty:
                return None
            close = df["Close"]
            # yfinance may return a single-column frame
            if isinstance(close, pd.DataFrame):
                close = close.iloc[:, 0]
            close.name = ticker
            return close.dropna()
        except Exception as exc:  # network / rate limit
            if attempt == retries - 1:
                print(f"  ! {ticker}: {exc}")
                return None
            time.sleep(2 * (attempt + 1))
    return None


def load_prices(
    tickers: list[str] | None = None,
    start: str = "2000-01-01",
    refresh: bool = False,
) -> pd.DataFrame:
    """Return a daily adjusted-close frame, one column per ticker.

    Results are cached to ``data/<ticker>.csv`` so repeated backtests do not
    re-hit the network. Assets with shorter histories are kept as NaN before
    inception rather than dropped -- the engine treats NaN as "not tradeable
    yet", so BTC simply enters the book in 2014.
    """
    tickers = tickers or all_tickers()
    CACHE_DIR.mkdir(parents=True, exist_ok=True)

    series: list[pd.Series] = []
    for ticker in tickers:
        path = _cache_path(ticker)
        if path.exists() and not refresh:
            s = pd.read_csv(path, index_col=0, parse_dates=True).iloc[:, 0]
            s.name = ticker
        else:
            print(f"  downloading {ticker} ...")
            s = _download_one(ticker, start)
            if s is None:
                print(f"  ! skipping {ticker} (no data)")
                continue
            s.to_frame().to_csv(path)
        series.append(s)

    if not series:
        raise RuntimeError("no price data could be loaded")

    prices = pd.concat(series, axis=1).sort_index()
    prices = prices[prices.index >= pd.Timestamp(start)]

    # Crypto trades weekends, which would push the index to ~365 rows a year
    # and silently corrupt every sqrt(252) annualisation. Snap everything to
    # the exchange calendar; a Monday crypto return then includes the weekend
    # move, which is exactly what a Mon-Fri book would actually capture.
    non_crypto = [c for c in prices.columns if c not in UNIVERSE.get("crypto", [])]
    if non_crypto:
        calendar = prices.index[prices[non_crypto].notna().any(axis=1)]
        prices = prices.reindex(calendar)

    # Forward-fill holidays/mismatched calendars, but never before inception.
    return prices.ffill()
