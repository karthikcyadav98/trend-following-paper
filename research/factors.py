"""Ken French factor data -- free, keyless, 1926 to present.

The question this answers: does the trend book earn anything the market does not
already give you? A strategy that merely re-expresses market beta is not an
edge, it is an expensive index fund. Regressing daily returns on Mkt-RF/SMB/HML
gives the alpha net of those exposures.
"""
import io, os, ssl, urllib.request, zipfile

URL = ("https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
       "F-F_Research_Data_Factors_daily_CSV.zip")
CACHE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "cache")


def _ctx():
    c = ssl.create_default_context()
    if c.cert_store_stats().get("x509_ca", 0) == 0:
        for p in ("/etc/ssl/cert.pem", "/etc/ssl/certs/ca-certificates.crt"):
            if os.path.exists(p):
                return ssl.create_default_context(cafile=p)
    return c


def load():
    """DataFrame indexed by date with Mkt-RF, SMB, HML, RF as daily decimals."""
    import pandas as pd
    os.makedirs(CACHE, exist_ok=True)
    path = os.path.join(CACHE, "ff_daily.zip")
    if not os.path.exists(path):
        req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"})
        with urllib.request.urlopen(req, timeout=60, context=_ctx()) as r:
            open(path, "wb").write(r.read())
    z = zipfile.ZipFile(path)
    raw = z.read(z.namelist()[0]).decode("latin-1").splitlines()
    rows = [l for l in raw if l.strip() and l.strip()[0].isdigit() and len(l.split(",")[0].strip()) == 8]
    df = pd.read_csv(io.StringIO("Date,Mkt-RF,SMB,HML,RF\n" + "\n".join(rows)))
    df["Date"] = pd.to_datetime(df["Date"], format="%Y%m%d")
    df = df.set_index("Date")
    return df.astype(float) / 100.0


def alpha(returns, ff=None):
    """OLS of strategy returns on the three factors. Returns annualised alpha + t."""
    import numpy as np, pandas as pd
    ff = load() if ff is None else ff
    d = pd.concat([returns.rename("r"), ff], axis=1, join="inner").dropna()
    y = (d["r"] - d["RF"]).values
    X = np.column_stack([np.ones(len(d)), d["Mkt-RF"], d["SMB"], d["HML"]])
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    dof = len(y) - X.shape[1]
    s2 = resid @ resid / dof
    se = np.sqrt(np.diag(s2 * np.linalg.inv(X.T @ X)))
    return {"alpha_daily": beta[0], "alpha_annual": beta[0] * 252,
            "t_alpha": beta[0] / se[0], "beta_mkt": beta[1], "beta_smb": beta[2],
            "beta_hml": beta[3], "n": len(d),
            "resid_sd": float(np.std(resid, ddof=1))}
