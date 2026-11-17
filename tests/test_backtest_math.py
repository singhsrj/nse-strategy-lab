"""The engine's arithmetic, checked against cases with known answers."""
import numpy as np
import pandas as pd

import config as C
from engine.backtest import run
from engine.data import load_prices
from engine.strategies import _weights

PRICES = load_prices().loc["2015":"2017"]
NIFTY_R = PRICES[C.NIFTY].pct_change()
ZERO = dict(cost=0.0, borrow=0.0, cash_rate=0.0)


def all_cash(prices):
    return _weights(prices, {})


def short_nifty(prices):
    return _weights(prices, {C.NIFTY: -1.0})


def test_buy_hold_zero_cost_equals_nifty():
    eq = run("buy_hold", PRICES, **ZERO)["equity"]
    # Decided at day 0, filled at day 1's close, so it tracks NIFTY from day 2 on.
    np.testing.assert_allclose(eq.pct_change().iloc[2:], NIFTY_R.iloc[2:], atol=1e-12)
    assert np.isclose(eq.iloc[-1] / eq.iloc[1], PRICES[C.NIFTY].iloc[-1] / PRICES[C.NIFTY].iloc[1])


def test_all_cash_earns_cash_rate():
    eq = run(all_cash, PRICES)["equity"]
    np.testing.assert_allclose(eq.pct_change().iloc[1:], C.CASH_RATE / C.TRADING_DAYS, atol=1e-15)


def test_short_gains_when_index_falls():
    # threshold 0 -> re-shorted back to exactly -100% every day, so day return = -index return.
    res = run(short_nifty, PRICES, threshold=0.0, **ZERO)
    r = res["equity"].pct_change().iloc[2:]
    np.testing.assert_allclose(r, -NIFTY_R.iloc[2:], atol=1e-12)
    falls = NIFTY_R.iloc[2:] < 0
    assert (r[falls] > 0).all() and (r[~falls & (NIFTY_R.iloc[2:] > 0)] < 0).all()
    # Borrow fee appears as -size x daily rate on every day the short is held.
    with_fee = run(short_nifty, PRICES, threshold=0.0, cost=0.0, cash_rate=0.0, borrow=0.02)
    r2 = with_fee["equity"].pct_change().iloc[2:]
    np.testing.assert_allclose(r2, -NIFTY_R.iloc[2:] - 0.02 / C.TRADING_DAYS, atol=1e-12)


def test_no_trades_no_cost():
    cheap = run(all_cash, PRICES, cost=0.0)
    pricey = run(all_cash, PRICES, cost=0.05)
    assert pricey["trades"] == []
    pd.testing.assert_series_equal(cheap["equity"], pricey["equity"])
