"""No strategy may see the future: faking every price after date D (x10) must not change the decision at D."""
import pandas as pd
import pytest

import config as C
from engine.data import load_prices
from engine.strategies import REGISTRY, weights_on

PRICES = load_prices()
DATES = ["2008-10-24", "2009-03-09", "2013-08-28", "2016-02-29", "2020-03-23", "2022-06-17"]


def with_fake_future(prices: pd.DataFrame, date: str) -> pd.DataFrame:
    """Real prices up to `date`; every later price x10, plus 30 extra fake days."""
    fake = prices.copy()
    fake.loc[fake.index > date] *= 10
    extra_days = pd.bdate_range(fake.index[-1] + pd.Timedelta(days=1), periods=30)
    extra = pd.DataFrame([fake.iloc[-1] * 10] * 30, index=extra_days)
    return pd.concat([fake, extra])


@pytest.mark.parametrize("sid", list(REGISTRY))
@pytest.mark.parametrize("date", DATES)
def test_future_prices_do_not_change_decision(sid, date):
    real = weights_on(sid, PRICES, date)
    faked = weights_on(sid, with_fake_future(PRICES, date), date)
    pd.testing.assert_series_equal(real, faked)


def test_the_test_has_teeth():
    """If a strategy were handed the full frame, the fake future WOULD change its decision."""
    date = "2008-10-24"                                  # NIFTY far below its 200-day average
    assert weights_on("trend", PRICES, date)[C.NIFTY] == 0.0
    leaked = REGISTRY["trend"]["fn"](with_fake_future(PRICES, date))
    assert leaked[C.NIFTY] == 1.0
