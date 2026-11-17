"""Parameter grids: does the result depend on one lucky setting?  Run: uv run python -m engine.sensitivity

Each setting is backtested on the full history; Sharpe and max drawdown are measured out-of-sample.
The headline defaults in REGISTRY are NOT changed to whatever wins here.
"""
import itertools

import pandas as pd

import config as C
from engine.backtest import run
from engine.data import load_prices
from engine.metrics import scorecard
from engine.strategies import REGISTRY

GRIDS = {
    "trend": {"ma": [50, 100, 150, 200, 250]},
    "sector_mom": {"lookback": [63, 126, 189, 252], "top": [2, 3, 4]},   # 3/6/9/12 months
    "voltarget": {"target": [0.08, 0.10, 0.12, 0.15], "window": [10, 20, 60]},
}


def sensitivity(prices: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for sid, grid in GRIDS.items():
        for values in itertools.product(*grid.values()):
            params = dict(zip(grid, values))
            oos = scorecard(run(sid, prices, **params), C.OUT_SAMPLE_START)
            is_default = all(REGISTRY[sid]["params"][k] == v for k, v in params.items())
            rows.append({"strategy": sid, "params": ", ".join(f"{k}={v}" for k, v in params.items()),
                         "default": "*" if is_default else "", "oos_return": oos["ann_return"],
                         "oos_sharpe": oos["sharpe"], "oos_max_dd": oos["max_dd"]})
            print(f"{sid:10s} {rows[-1]['params']:22s} sharpe {oos['sharpe']:+.2f}  max_dd {oos['max_dd']:.1%}")
    return pd.DataFrame(rows)


def pivot(df: pd.DataFrame, sid: str, value: str) -> pd.DataFrame:
    """Grid view for a two-parameter strategy (rows = first param, cols = second)."""
    d = df[df.strategy == sid].copy()
    keys = list(GRIDS[sid])
    for i, k in enumerate(keys):
        d[k] = pd.to_numeric(d.params.str.split(", ").str[i].str.split("=").str[1])
    return d.pivot(index=keys[0], columns=keys[1], values=value) if len(keys) == 2 else d.set_index(keys[0])[[value]]


if __name__ == "__main__":
    df = sensitivity(load_prices())
    C.REPORTS_DIR.mkdir(exist_ok=True)
    df.to_csv(C.REPORTS_DIR / "sensitivity.csv", index=False, float_format="%.4f")
    for sid in GRIDS:
        for value, fmt in [("oos_sharpe", "{:+.2f}"), ("oos_max_dd", "{:.1%}")]:
            print(f"\n## {sid}: {value}  (default: {REGISTRY[sid]['params']})\n")
            print(pivot(df, sid, value).map(fmt.format).to_markdown())
