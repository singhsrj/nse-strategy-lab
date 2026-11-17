"""Download, clean, cache and check NSE index closes.

Run:  uv run python -m engine.data            (uses cache if present)
      uv run python -m engine.data --refresh  (re-downloads)
"""
import sys

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd
import yfinance as yf

import config as C


def download(tickers=C.TICKERS, start=C.START_DATE) -> pd.DataFrame:
    """Daily closes, one column per ticker. Tickers that return nothing are dropped."""
    raw = yf.download(tickers, start=start, auto_adjust=False, progress=False, threads=True)
    # yfinance returns MultiIndex columns (field, ticker); keep only Close.
    closes = raw["Close"] if isinstance(raw.columns, pd.MultiIndex) else raw[["Close"]]
    closes.index = pd.to_datetime(closes.index).tz_localize(None)
    closes = closes.dropna(axis=1, how="all")
    return closes[[t for t in tickers if t in closes.columns]]


def bad_ticks(df: pd.DataFrame) -> pd.DataFrame:
    """True where a price is more than 2x away from its 11-day median (e.g. a botched split).
    This is a one-off data repair, not a trading signal, so a centred window is fine here."""
    med = df.rolling(11, center=True, min_periods=3).median()
    ratio = df / med
    return (ratio > 2) | (ratio < 0.5)


def clean(closes: pd.DataFrame) -> pd.DataFrame:
    """Align on NIFTY trading days, blank out bad ticks, forward-fill short gaps only."""
    nifty_days = closes[C.NIFTY].dropna().index
    df = closes.reindex(nifty_days)
    bad = bad_ticks(df)
    for t in df.columns[bad.any()]:
        print(f"Repaired bad ticks in {t}: {[d.date() for d in df.index[bad[t]]]}")
    return df.mask(bad).ffill(limit=C.MAX_FFILL_DAYS)


def load_prices(refresh: bool = False) -> pd.DataFrame:
    """Cached prices; downloads and saves on first use."""
    if C.PRICES_CSV.exists() and not refresh:
        return pd.read_csv(C.PRICES_CSV, index_col=0, parse_dates=True)
    prices = clean(download())
    C.DATA_DIR.mkdir(exist_ok=True)
    prices.to_csv(C.PRICES_CSV, float_format="%.4f")
    return prices


def checks(prices: pd.DataFrame) -> pd.DataFrame:
    """Per ticker: first/last date, rows, missing days after its start, big moves."""
    rets = prices.pct_change(fill_method=None)
    rows = []
    for t in prices.columns:
        s = prices[t]
        first = s.first_valid_index()
        big = rets[t][rets[t].abs() > C.BIG_MOVE]
        rows.append({
            "ticker": t,
            "first": first.date(),
            "last": s.last_valid_index().date(),
            "rows": int(s.notna().sum()),
            "missing_after_start": int(s.loc[first:].isna().sum()),
            "big_moves": ", ".join(f"{d.date()} {r:+.1%}" for d, r in big.items()) or "-",
        })
    return pd.DataFrame(rows).set_index("ticker")


def chart_growth(prices: pd.DataFrame, path=C.REPORTS_DIR / "chart1_growth.png"):
    """Chart 1: growth of Rs 1 per asset, each from its own first date."""
    C.REPORTS_DIR.mkdir(exist_ok=True)
    growth = prices.apply(lambda s: s / s.dropna().iloc[0])
    fig, ax = plt.subplots(figsize=(11, 6))
    for t in growth.columns:
        lw, color = (2.5, "black") if t == C.NIFTY else (1.0, None)
        ax.plot(growth.index, growth[t], label=t, lw=lw, color=color)
    ax.set_yscale("log")
    ax.set_title("Growth of Rs 1 (price index, log scale)")
    ax.set_ylabel("Value of Rs 1")
    ax.grid(alpha=0.3, which="both")
    ax.legend(ncol=2, fontsize=8)
    fig.tight_layout()
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


if __name__ == "__main__":
    prices = load_prices(refresh="--refresh" in sys.argv)
    missing = [t for t in C.TICKERS if t not in prices.columns]
    sectors = [t for t in C.SECTORS if t in prices.columns]
    print(f"Loaded {len(prices.columns)}/{len(C.TICKERS)} tickers, "
          f"{len(prices)} NIFTY trading days "
          f"{prices.index[0].date()} -> {prices.index[-1].date()}")
    print(f"Sectors loaded: {len(sectors)} (need >= {C.MIN_SECTORS}); missing: {missing or 'none'}")
    pd.set_option("display.width", 250, "display.max_colwidth", 120)
    print(checks(prices).to_string())
    print("Chart 1 saved to", chart_growth(prices))
