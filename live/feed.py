"""Daily closes from Yahoo's chart endpoint -- stdlib only.

yfinance is used for the research backtest, but the hosted runner needs
something that cannot break on a dependency bump or a scraping change, so the
live path talks to the JSON chart endpoint directly.

Two hard-won details, both mandatory:
  * Yahoo 429s a full "...Chrome/120...Safari/537.36" user-agent and serves a
    short one. Do not "improve" this string.
  * python.org builds ship no CA bundle, so the SSL context falls back to
    certifi or the system bundle.
"""

import json
import os
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
HOSTS = ["https://query1.finance.yahoo.com", "https://query2.finance.yahoo.com"]
_SSL = None
_LAST = 0.0
MIN_GAP = 1.2          # Yahoo rate-limits rapid-fire requests


class FeedError(Exception):
    pass


def _ctx():
    global _SSL
    if _SSL is not None:
        return _SSL
    ctx = ssl.create_default_context()
    if ctx.cert_store_stats().get("x509_ca", 0) == 0:
        try:
            import certifi
            ctx = ssl.create_default_context(cafile=certifi.where())
        except ImportError:
            for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
                if os.path.exists(p):
                    ctx = ssl.create_default_context(cafile=p)
                    break
    _SSL = ctx
    return ctx


def _get(url, retries=4):
    global _LAST
    delay = 2.0
    for attempt in range(retries):
        wait = MIN_GAP - (time.time() - _LAST)
        if wait > 0:
            time.sleep(wait)
        _LAST = time.time()
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=25, context=_ctx()) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except urllib.error.HTTPError as e:
            if e.code in (429, 502, 503, 999) and attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
        except urllib.error.URLError:
            if attempt < retries - 1:
                time.sleep(delay)
                delay *= 2
                continue
            raise
    raise FeedError(f"exhausted retries: {url}")


def closes(ticker, rng="5y"):
    """[(date 'YYYY-MM-DD', close)] of completed daily bars, oldest first."""
    enc = urllib.parse.quote(ticker, safe="")
    last = None
    for host in HOSTS:
        try:
            payload = _get(f"{host}/v8/finance/chart/{enc}?range={rng}&interval=1d")
        except Exception as e:
            last = e
            continue
        chart = payload.get("chart") or {}
        if chart.get("error"):
            last = FeedError(f"{ticker}: {chart['error']}")
            continue
        res = (chart.get("result") or [None])[0]
        if not res:
            last = FeedError(f"{ticker}: empty result")
            continue
        stamps = res.get("timestamp") or []
        q = ((res.get("indicators") or {}).get("quote") or [{}])[0]
        adj = (res.get("indicators") or {}).get("adjclose")
        series = (adj[0].get("adjclose") if adj else None) or q.get("close")
        if not stamps or not series:
            last = FeedError(f"{ticker}: no close series")
            continue
        out = []
        for t, c in zip(stamps, series):
            if c is None:
                continue
            out.append((time.strftime("%Y-%m-%d", time.gmtime(t)), float(c)))
        if out:
            return out
        last = FeedError(f"{ticker}: all closes null")
    raise FeedError(f"{ticker}: {last}")


def frame(tickers, rng="5y"):
    """pandas DataFrame of aligned daily closes; missing days forward-filled."""
    import pandas as pd

    cols, errs = {}, []
    for t in tickers:
        try:
            rows = closes(t, rng)
            cols[t] = pd.Series({d: c for d, c in rows})
        except Exception as e:
            errs.append(f"{t}: {e}")
    if not cols:
        raise FeedError("no tickers fetched: " + "; ".join(errs))
    df = pd.DataFrame(cols)
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    # Holidays differ across venues (crypto trades weekends); forward-fill so a
    # single closed market does not blank the whole book.
    return df.ffill(), errs


def usdinr():
    """Live-ish USDINR so an Indian investor sees rupees, not dollars."""
    rows = closes("USDINR=X", rng="1mo")
    return rows[-1][1]
