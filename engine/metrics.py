"""Scorecard for a full period and running metrics for the replay."""
import numpy as np
import pandas as pd

import config as C

DAILY_CASH = C.CASH_RATE / C.TRADING_DAYS


def _sharpe(r: pd.Series) -> float:
    """Excess return over cash per unit of volatility, annualised."""
    sd = r.std()
    return float((r.mean() - DAILY_CASH) / sd * np.sqrt(C.TRADING_DAYS)) if sd > 0 else 0.0


def drawdown(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1


def scorecard(result: dict, start=None, end=None) -> dict:
    eq = result["equity"].loc[start:end]
    r = eq.pct_change().dropna()
    years = len(r) / C.TRADING_DAYS
    trades = pd.DataFrame(result["trades"])
    traded = 0.0
    if len(trades):
        traded = trades[(trades.date >= eq.index[0]) & (trades.date <= eq.index[-1])].weight.sum()
    monthly = eq.resample("ME").last().pct_change().dropna()
    return {
        "ann_return": (eq.iloc[-1] / eq.iloc[0]) ** (1 / years) - 1,
        "ann_vol": r.std() * np.sqrt(C.TRADING_DAYS),
        "sharpe": _sharpe(r),
        "max_dd": drawdown(eq).min(),
        "worst_month": monthly.min(),
        "turnover": traded / years,               # sum of |weight traded| per year
    }


MIN_DAYS = 20   # annualising fewer days than this gives meaningless vol/Sharpe


def running_metrics(equity: pd.Series) -> dict:
    """Metrics using only the equity seen so far (used by the replay). Vol/Sharpe are None until MIN_DAYS."""
    r = equity.pct_change().dropna()
    dd = drawdown(equity)
    enough = len(r) >= MIN_DAYS
    return {
        "return": float(equity.iloc[-1] / equity.iloc[0] - 1),
        "vol": float(r.std() * np.sqrt(C.TRADING_DAYS)) if enough else None,
        "sharpe": _sharpe(r) if enough else None,
        "max_dd": float(dd.min()),
        "current_dd": float(dd.iloc[-1]),
    }
