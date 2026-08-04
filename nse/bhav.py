"""NSE bhavcopy: the whole Indian cash market, one file per trading day.

Free, keyless, and -- the reason it is worth the download effort -- POINT IN
TIME. Every file lists what was actually trading that day, including names that
have since been delisted or renamed. Building a universe this way avoids
survivorship bias, which is the single biggest source of fake backtest returns
in equity research: pick today's Nifty 500 and test it over ten years and you
have quietly guaranteed that every company in your sample survived.

NSE changed the format in July 2024, so both are parsed:
  old  SYMBOL,SERIES,OPEN,...,CLOSE,...,TOTTRDQTY,TOTTRDVAL,TIMESTAMP,...
  new  TradDt,...,TckrSymb,SctySrs,...,ClsPric,...,TtlTradgVol,TtlTrfVal,...
"""

import datetime as dt
import io
import os
import ssl
import time
import urllib.error
import urllib.request
import zipfile

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE = os.path.join(ROOT, "cache", "nse")
NEW_FROM = dt.date(2024, 7, 8)          # new archive format starts here
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]
_SSL = None


def _ctx():
    global _SSL
    if _SSL is None:
        c = ssl.create_default_context()
        if c.cert_store_stats().get("x509_ca", 0) == 0:
            for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
                if os.path.exists(p):
                    c = ssl.create_default_context(cafile=p)
                    break
        _SSL = c
    return _SSL


def _url(d):
    if d >= NEW_FROM:
        return ("https://nsearchives.nseindia.com/content/cm/"
                f"BhavCopy_NSE_CM_0_0_0_{d:%Y%m%d}_F_0000.csv.zip")
    return ("https://nsearchives.nseindia.com/content/historical/EQUITIES/"
            f"{d.year}/{MONTHS[d.month - 1]}/cm{d.day:02d}{MONTHS[d.month - 1]}{d.year}bhav.csv.zip")


def fetch_day(d, retries=2):
    """Rows for one date: [(symbol, close, volume, value)]. [] if not a trading day."""
    os.makedirs(CACHE, exist_ok=True)
    cached = os.path.join(CACHE, f"{d:%Y%m%d}.zip")
    miss = os.path.join(CACHE, f"{d:%Y%m%d}.absent")
    if os.path.exists(miss):
        return []
    if not os.path.exists(cached):
        for attempt in range(retries + 1):
            try:
                req = urllib.request.Request(_url(d), headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30, context=_ctx()) as r:
                    blob = r.read()
                open(cached, "wb").write(blob)
                break
            except urllib.error.HTTPError as e:
                if e.code == 404:                      # holiday / weekend
                    open(miss, "w").close()
                    return []
                if attempt == retries:
                    raise
                time.sleep(1.5)
            except Exception:
                if attempt == retries:
                    raise
                time.sleep(1.5)
    try:
        z = zipfile.ZipFile(cached)
    except zipfile.BadZipFile:
        os.remove(cached)
        return []
    text = z.read(z.namelist()[0]).decode("utf-8", "replace")
    lines = text.splitlines()
    if len(lines) < 2:
        return []
    head = [h.strip() for h in lines[0].split(",")]
    out = []
    if "TckrSymb" in head:                              # new format
        i = {k: head.index(k) for k in ("TckrSymb", "SctySrs", "ClsPric", "TtlTradgVol", "TtlTrfVal")}
        for ln in lines[1:]:
            p = ln.split(",")
            if len(p) <= max(i.values()) or p[i["SctySrs"]].strip() != "EQ":
                continue
            try:
                out.append((p[i["TckrSymb"]].strip(), float(p[i["ClsPric"]]),
                            float(p[i["TtlTradgVol"]] or 0), float(p[i["TtlTrfVal"]] or 0)))
            except ValueError:
                continue
    else:                                               # old format
        i = {k: head.index(k) for k in ("SYMBOL", "SERIES", "CLOSE", "TOTTRDQTY", "TOTTRDVAL")}
        for ln in lines[1:]:
            p = ln.split(",")
            if len(p) <= max(i.values()) or p[i["SERIES"]].strip() != "EQ":
                continue
            try:
                out.append((p[i["SYMBOL"]].strip(), float(p[i["CLOSE"]]),
                            float(p[i["TOTTRDQTY"]] or 0), float(p[i["TOTTRDVAL"]] or 0)))
            except ValueError:
                continue
    return out


def panel(start, end, verbose=True):
    """(closes, turnover) DataFrames indexed by date, columns = symbols."""
    import pandas as pd

    closes, turn = {}, {}
    d, n_days, fetched = start, 0, 0
    while d <= end:
        if d.weekday() < 5:
            rows = fetch_day(d)
            if rows:
                closes[d] = {s: c for s, c, _v, _t in rows}
                turn[d] = {s: t for s, _c, _v, t in rows}
                fetched += 1
            n_days += 1
            if verbose and n_days % 100 == 0:
                print(f"    {d} … {fetched} trading days", flush=True)
        d += dt.timedelta(days=1)
    px = pd.DataFrame(closes).T.sort_index()
    tv = pd.DataFrame(turn).T.sort_index()
    px.index = pd.to_datetime(px.index)
    tv.index = pd.to_datetime(tv.index)
    return px, tv
