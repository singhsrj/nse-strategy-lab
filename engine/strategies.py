"""The six strategies. Each one: f(prices up to today, **params) -> target weights for today.

Weights are indexed by asset plus a 'CASH' entry. Negative = short.
CASH = 1 - sum of long weights (shorts don't free up or use cash; they pay a borrow fee in the engine).
"""
import numpy as np
import pandas as pd

import config as C


def _weights(prices: pd.DataFrame, held: dict) -> pd.Series:
    """Turn {asset: weight} into a full weight Series with a CASH entry."""
    w = pd.Series(0.0, index=list(prices.columns) + ["CASH"])
    for asset, weight in held.items():
        w[asset] = weight
    w["CASH"] = 1.0 - sum(x for x in held.values() if x > 0)
    return w


def _month_start_slice(prices: pd.DataFrame) -> pd.DataFrame:
    """Prices up to the end of the previous month: monthly strategies only use completed months."""
    first_of_month = prices.index[-1].replace(day=1)
    return prices[prices.index < first_of_month]


def _sector_returns(prices: pd.DataFrame, lookback: int) -> pd.Series:
    """Lookback-day return per sector as of the last row; sectors without enough history are dropped."""
    sectors = prices[[s for s in C.SECTORS if s in prices.columns]]
    if len(sectors) <= lookback:
        return pd.Series(dtype=float)
    return (sectors.iloc[-1] / sectors.iloc[-1 - lookback] - 1).dropna()


def trend(prices, ma=200):
    p = prices[C.NIFTY]
    above = len(p) >= ma and p.iloc[-1] > p.iloc[-ma:].mean()
    return _weights(prices, {C.NIFTY: 1.0} if above else {})


def trend_ls(prices, ma=200, short=0.5):
    p = prices[C.NIFTY]
    if len(p) < ma:
        return _weights(prices, {})
    above = p.iloc[-1] > p.iloc[-ma:].mean()
    return _weights(prices, {C.NIFTY: 1.0 if above else -short})


def sector_mom(prices, lookback=252, top=3):
    rets = _sector_returns(_month_start_slice(prices), lookback)
    winners = rets.sort_values(ascending=False).head(top)
    winners = winners[winners > 0]                      # negative ones go to cash
    return _weights(prices, {s: 1.0 / top for s in winners.index})


def sector_ls(prices, lookback=252, n=3):
    rets = _sector_returns(_month_start_slice(prices), lookback).sort_values(ascending=False)
    if len(rets) < 2 * n:                               # need distinct longs and shorts
        return _weights(prices, {})
    size = 1.0 / (2 * n)
    held = {s: size for s in rets.index[:n]} | {s: -size for s in rets.index[-n:]}
    return _weights(prices, held)


def voltarget(prices, target=0.12, window=20):
    r = prices[C.NIFTY].pct_change().iloc[-window:]
    if len(prices) <= window:
        return _weights(prices, {})
    vol = r.std() * np.sqrt(C.TRADING_DAYS)
    return _weights(prices, {C.NIFTY: min(target / vol, 1.0)})


def buy_hold(prices):
    return _weights(prices, {C.NIFTY: 1.0})


REGISTRY = {
    "trend": dict(fn=trend, name="Trend NIFTY", style="Long only", params=dict(ma=200),
                  description="100% NIFTY when above its 200-day average, else cash."),
    "trend_ls": dict(fn=trend_ls, name="Trend long/short", style="Long-short",
                     params=dict(ma=200, short=0.5),
                     description="+100% NIFTY above its 200-day average, -50% NIFTY below."),
    "sector_mom": dict(fn=sector_mom, name="Sector momentum", style="Long only",
                       params=dict(lookback=252, top=3),
                       description="Monthly: top 3 sectors by 12-month return, equal weight; negative ones to cash."),
    "sector_ls": dict(fn=sector_ls, name="Sector long/short", style="Market-neutral",
                      params=dict(lookback=252, n=3),
                      description="Monthly: long top 3 sectors at +1/6 each, short bottom 3 at -1/6 each."),
    "voltarget": dict(fn=voltarget, name="Vol-targeted NIFTY", style="Long only",
                      params=dict(target=0.12, window=20),
                      description="NIFTY weight = min(12% / 20-day volatility, 1), rest in cash."),
    "buy_hold": dict(fn=buy_hold, name="Buy and hold NIFTY", style="Baseline", params={},
                     description="100% NIFTY, always."),
}


def weights_on(strategy, prices: pd.DataFrame, date, **params) -> pd.Series:
    """The ONLY way to get a decision: the strategy sees prices up to `date`, never beyond.
    `strategy` is a REGISTRY id or a plain function (used by tests)."""
    if isinstance(strategy, str):
        fn, params = REGISTRY[strategy]["fn"], REGISTRY[strategy]["params"] | params
    else:
        fn = strategy
    return fn(prices.loc[:date], **params)


if __name__ == "__main__":
    from engine.data import load_prices
    prices = load_prices()
    for date in ["2009-03-02", "2020-03-23", "2021-06-01", str(prices.index[-1].date())]:
        print(f"\n=== Decisions at close of {date} ===")
        for sid in REGISTRY:
            w = weights_on(sid, prices, date)
            pos = w.drop("CASH")
            held = ", ".join(f"{a} {x:+.2f}" for a, x in pos[pos != 0].items()) or "-"
            print(f"{sid:11s} gross {pos.abs().sum():.2f}  net {pos.sum():+.2f}  "
                  f"cash {w['CASH']:.2f}  | {held}")
