"""Scorecards, stress table and charts into reports/.  Run: uv run python -m engine.report"""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

import config as C
from engine.backtest import run_all
from engine.data import load_prices
from engine.metrics import drawdown, scorecard
from engine.strategies import REGISTRY

# Fixed colour per strategy (never by rank); the NIFTY baseline is dark grey.
COLORS = {"trend": "#2a78d6", "trend_ls": "#eb6834", "sector_mom": "#1baf7a",
          "sector_ls": "#eda100", "voltarget": "#e87ba4", "buy_hold": "#333333"}
PERIODS = {"full": (None, None), "in_sample": (None, C.IN_SAMPLE_END),
           "out_of_sample": (C.OUT_SAMPLE_START, None)}
STRESS = {"2008": ("2008-01-01", "2008-12-31"), "Feb-Apr 2020": ("2020-02-01", "2020-04-30")}


def scorecards(results) -> pd.DataFrame:
    rows = [{"period": p, "strategy": sid, **scorecard(res, *span)}
            for p, span in PERIODS.items() for sid, res in results.items()]
    return pd.DataFrame(rows).set_index(["period", "strategy"])


def stress(results) -> pd.DataFrame:
    rows = {}
    for sid, res in results.items():
        eq = res["equity"]
        row = {name: eq.loc[a:b].iloc[-1] / eq.loc[a:b].iloc[0] - 1 for name, (a, b) in STRESS.items()}
        row["worst_dd_since_2021"] = drawdown(eq.loc["2021-01-01":]).min()
        rows[sid] = row
    return pd.DataFrame(rows).T


def charts(results):
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(11, 8), sharex=True,
                                   gridspec_kw=dict(height_ratios=[2, 1]))
    for sid, res in results.items():
        lw = 2.5 if sid == "buy_hold" else 1.6
        ax1.plot(res["equity"], color=COLORS[sid], lw=lw, label=REGISTRY[sid]["name"])
        ax2.plot(drawdown(res["equity"]), color=COLORS[sid], lw=1.2)
    ax1.set_yscale("log")
    ax1.set_yticks([0.5, 1, 2, 3, 4, 6])
    ax1.yaxis.set_major_formatter(matplotlib.ticker.FuncFormatter(lambda v, _: f"Rs {v:g}"))
    ax1.yaxis.set_minor_formatter(matplotlib.ticker.NullFormatter())
    ax1.set_title("Growth of Rs 1 after costs (log scale)")
    ax1.legend(fontsize=8, frameon=False)
    ax2.set_title("Drawdown from previous peak")
    ax2.yaxis.set_major_formatter(matplotlib.ticker.PercentFormatter(1.0))
    for ax in (ax1, ax2):
        ax.axvline(pd.Timestamp(C.OUT_SAMPLE_START), color="#999999", ls="--", lw=1)
        ax.grid(alpha=0.25, which="both")
        ax.spines[["top", "right"]].set_visible(False)
    ax1.text(pd.Timestamp(C.OUT_SAMPLE_START), ax1.get_ylim()[1], " out-of-sample ->",
             va="top", fontsize=8, color="#666666")
    fig.tight_layout()
    path = C.REPORTS_DIR / "chart2_equity_drawdown.png"
    fig.savefig(path, dpi=120)
    plt.close(fig)
    return path


if __name__ == "__main__":
    prices = load_prices()
    results = run_all(prices)
    C.REPORTS_DIR.mkdir(exist_ok=True)
    sc, st = scorecards(results), stress(results)
    sc.to_csv(C.REPORTS_DIR / "scorecard.csv", float_format="%.4f")
    st.to_csv(C.REPORTS_DIR / "stress.csv", float_format="%.4f")
    pct = lambda x: f"{x:+.1%}"
    fmt = {"ann_return": pct, "ann_vol": "{:.1%}".format, "sharpe": "{:.2f}".format,
           "max_dd": pct, "worst_month": pct, "turnover": "{:.2f}".format}
    for period in PERIODS:
        print(f"\n## Scorecard: {period}\n")
        print(sc.loc[period].apply(lambda c: c.map(fmt[c.name])).to_markdown())
    print("\n## Stress\n")
    print(st.map(pct).to_markdown())
    print("\nTrades per strategy:", {sid: len(r["trades"]) for sid, r in results.items()})
    print("Chart saved to", charts(results))
