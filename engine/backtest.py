"""Weights -> trades -> costs -> equity, one day at a time. Supports shorts.

Timeline for day i:
  1. Earn day i's return on the weights held since close i-1 (then weights drift).
  2. At close i, fill the target decided at close i-1 (threshold, cost, trade log).
  3. At close i, ask the strategy for a new target using prices up to day i only.
"""
import numpy as np
import pandas as pd

import config as C
from engine.strategies import weights_on


def _sides(w0: float, w1: float):
    """Split a weight change into BUY / SELL / SHORT / COVER legs: [(side, size), ...]."""
    legs = []
    if w0 > 0 and w1 < w0:                       # reduce or close a long
        legs.append(("SELL", w0 - max(w1, 0.0)))
    if w0 < 0 and w1 > w0:                       # reduce or close a short
        legs.append(("COVER", min(w1, 0.0) - w0))
    if w1 > 0 and w1 > w0:                       # open or add to a long
        legs.append(("BUY", w1 - max(w0, 0.0)))
    if w1 < 0 and w1 < w0:                       # open or add to a short
        legs.append(("SHORT", min(w0, 0.0) - w1))
    return legs


def run(strategy, prices: pd.DataFrame, cost=C.COST, borrow=C.BORROW_RATE, cash_rate=C.CASH_RATE,
        threshold=C.REBALANCE_THRESHOLD, gross_cap=C.GROSS_CAP, **params) -> dict:
    """Backtest one strategy (REGISTRY id or function). Equity starts at 1.0."""
    assets = list(prices.columns)
    rets = prices.pct_change(fill_method=None).fillna(0.0).to_numpy()
    px = prices.to_numpy()
    cash_d, borrow_d = cash_rate / C.TRADING_DAYS, borrow / C.TRADING_DAYS

    n, k = len(prices), len(assets)
    w = np.zeros(k)                               # weights held right now (assets only)
    equity = np.ones(n)
    held = np.zeros((n, k))
    trades, target = [], None

    for i in range(n):
        date = prices.index[i]
        # 1. Day i return on yesterday's weights, then drift.
        if i > 0:
            cash_w = 1.0 - w[w > 0].sum()
            short_size = -w[w < 0].sum()
            r_p = w @ rets[i] + cash_w * cash_d - short_size * borrow_d
            equity[i] = equity[i - 1] * (1 + r_p)
            w = w * (1 + rets[i]) / (1 + r_p)

        # 2. Fill yesterday's decision at today's close.
        if target is not None:
            change = np.where(np.abs(target - w) > threshold, target - w, 0.0)
            turnover = np.abs(change).sum()
            if turnover > 0:
                equity[i] *= 1 - cost * turnover
                for j in np.flatnonzero(change):
                    for side, size in _sides(w[j], target[j]):
                        trades.append(dict(date=date, side=side, asset=assets[j],
                                           weight=round(float(size), 4), price=float(px[i, j])))
                w = w + change
        held[i] = w

        # 3. Decide at today's close using prices up to today only.
        t = weights_on(strategy, prices, date, **params).reindex(assets).fillna(0.0).to_numpy()
        gross = np.abs(t).sum()
        target = t * (gross_cap / gross) if gross > gross_cap else t

    weights = pd.DataFrame(held, index=prices.index, columns=assets)
    weights["CASH"] = 1.0 - weights[assets].clip(lower=0).sum(axis=1)
    return dict(equity=pd.Series(equity, index=prices.index, name="equity"),
                weights=weights, trades=trades)


def run_all(prices: pd.DataFrame) -> dict:
    """All REGISTRY strategies, one process each (they are independent)."""
    from concurrent.futures import ProcessPoolExecutor
    from engine.strategies import REGISTRY
    with ProcessPoolExecutor() as pool:
        futures = {sid: pool.submit(run, sid, prices) for sid in REGISTRY}
        return {sid: f.result() for sid, f in futures.items()}


RESULTS_PKL = C.DATA_DIR / "results.pkl"


def fingerprint() -> str:
    """Hash of the price data, settings and engine code: any change means results must be recomputed."""
    import hashlib
    h = hashlib.sha256(C.PRICES_CSV.read_bytes())
    for f in [C.ROOT / "config.py", *sorted((C.ROOT / "engine").glob("*.py"))]:
        h.update(f.read_bytes())
    return h.hexdigest()


def load_or_run_all(prices: pd.DataFrame) -> dict:
    """Saved results if they match the current data and code, otherwise run everything and save."""
    import pickle
    fp = fingerprint()
    if RESULTS_PKL.exists():
        saved = pickle.loads(RESULTS_PKL.read_bytes())
        if saved["fingerprint"] == fp:
            return saved["results"]
    results = run_all(prices)
    RESULTS_PKL.write_bytes(pickle.dumps({"fingerprint": fp, "results": results}))
    return results


if __name__ == "__main__":          # used by the deploy build step: precompute once
    import time
    from engine.data import load_prices
    t = time.time()
    load_or_run_all(load_prices())
    print(f"results ready in {RESULTS_PKL} ({time.time() - t:.1f}s)")
