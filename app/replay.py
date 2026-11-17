"""Slice precomputed backtests into replay ticks. Nothing here runs a backtest."""
import pandas as pd

import config as C
from engine.metrics import running_metrics


class Replay:
    def __init__(self, prices: pd.DataFrame, results: dict):
        self.prices = prices
        self.dates = prices.index
        self.results = results
        # trades grouped by date for fast lookup: {sid: {Timestamp: [trade, ...]}}
        self.trades = {sid: {} for sid in results}
        for sid, res in results.items():
            for t in res["trades"]:
                self.trades[sid].setdefault(t["date"], []).append(
                    {"side": t["side"], "asset": t["asset"], "weight": t["weight"]})

    def start_pos(self, start_date: str) -> int:
        """First trading day on or after start_date (clamped to the data)."""
        return min(int(self.dates.searchsorted(pd.Timestamp(start_date))), len(self.dates) - 1)

    def _rebased(self, sid: str, start: int, pos: int) -> pd.Series:
        eq = self.results[sid]["equity"].iloc[start:pos + 1]
        return eq / eq.iloc[0] * C.START_CAPITAL

    def strategy_tick(self, sid: str, start: int, pos: int) -> dict:
        eq = self._rebased(sid, start, pos)
        w = self.results[sid]["weights"].iloc[pos]
        assets = w.drop("CASH")
        return {
            "equity": round(float(eq.iloc[-1]), 2),
            "day_return": round(float(eq.iloc[-1] / eq.iloc[-2] - 1), 6) if len(eq) > 1 else 0.0,
            "positions": {a: round(float(x), 4) for a, x in w.items() if abs(x) > 1e-9},
            "gross": round(float(assets.abs().sum()), 4),
            "net": round(float(assets.sum()), 4),
            "trades_today": self.trades[sid].get(self.dates[pos], []),
            "running": {k: None if v is None else round(v, 4) for k, v in running_metrics(eq).items()},
        }

    def tick(self, strategies: list, start: int, pos: int) -> dict:
        return {
            "date": str(self.dates[pos].date()),
            "nifty_close": round(float(self.prices[C.NIFTY].iloc[pos]), 2),
            "strategies": {sid: self.strategy_tick(sid, start, pos) for sid in strategies},
        }

    def history(self, sid: str, start: int, pos: int) -> dict:
        """Everything from the start date to the current date, sent once when a strategy is added mid-replay."""
        eq = self._rebased(sid, start, pos)
        trades = [{"date": str(d.date()), **t}
                  for d in self.dates[start:pos + 1] for t in self.trades[sid].get(d, [])]
        return {"history": {"id": sid, "dates": [str(d.date()) for d in eq.index],
                            "equity": [round(float(x), 2) for x in eq],
                            "trades": trades,
                            "latest": self.strategy_tick(sid, start, pos)}}

    def nifty_history(self, start: int, pos: int) -> dict:
        p = self.prices[C.NIFTY].iloc[start:pos + 1]
        return {"dates": [str(d.date()) for d in p.index], "close": [round(float(x), 2) for x in p]}
