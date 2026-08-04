"""Traded universe for the live book.

Duplicated from `trend.data.UNIVERSE` on purpose: that module imports yfinance
at module scope, and the hosted runner should not need a scraping library it
never calls. `check_matches_backtest()` exists so the copy cannot drift silently
-- it is asserted in CI.
"""

UNIVERSE = {
    "equity": ["SPY", "QQQ", "EFA", "EEM"],
    "rates": ["TLT", "IEF"],
    "commodity": ["GLD", "SLV", "DBC", "USO"],
    "fx": ["UUP", "FXE", "FXY"],
    "crypto": ["BTC-USD", "ETH-USD"],
}


def all_tickers():
    return [t for g in UNIVERSE.values() for t in g]


def check_matches_backtest():
    """Raise if this copy has drifted from the backtest's universe."""
    from trend.data import UNIVERSE as REAL
    if REAL != UNIVERSE:
        raise AssertionError(f"live universe drifted from trend.data.UNIVERSE:\n{REAL}\n{UNIVERSE}")
    return True
