"""End-to-end replay over the real app: cookie session, REST controls, WebSocket ticks."""
import pandas as pd
import pytest
from fastapi.testclient import TestClient

import config as C
from app.main import STATE, app

START = "2020-03-02"


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:          # runs startup: precompute all backtests once
        assert c.get("/").status_code == 200
        assert "sid" in c.cookies
        yield c


def next_tick(ws):
    """Skip reset/history messages; return the next day tick."""
    while True:
        msg = ws.receive_json()
        if "date" in msg or "done" in msg:
            return msg


def expected_equity(sid, date):
    eq = STATE["replay"].results[sid]["equity"]
    return eq.loc[date] / eq.loc[START:].iloc[0] * C.START_CAPITAL


def test_strategies_endpoint(client):
    ids = [s["id"] for s in client.get("/api/strategies").json()]
    assert ids == ["trend", "trend_ls", "sector_mom", "sector_ls", "voltarget", "buy_hold"]


def test_replay_ticks_match_backtest_and_remove_drops(client):
    client.post("/api/session/strategies", json={"add": "trend_ls"})
    client.post("/api/session/strategies", json={"add": "buy_hold"})
    client.post("/api/session/replay", json={"start_date": START, "speed": 60})

    with client.websocket_connect("/ws") as ws:
        first = ws.receive_json()
        assert first["reset"] and first["state"]["current_date"] == START
        client.post("/api/session/replay", json={"action": "play"})

        ticks = [next_tick(ws) for _ in range(5)]
        dates = [t["date"] for t in ticks]
        assert dates == sorted(dates) and len(set(dates)) == 5 and dates[0] > START
        for t in ticks:
            for sid in ("trend_ls", "buy_hold"):
                assert t["strategies"][sid]["equity"] == pytest.approx(expected_equity(sid, t["date"]), abs=0.01)

        client.post("/api/session/strategies", json={"remove": "buy_hold"})
        after = [next_tick(ws) for _ in range(3)]
        assert "buy_hold" not in after[-1]["strategies"]       # at most one tick was already in flight
        assert "trend_ls" in after[-1]["strategies"]
        client.post("/api/session/replay", json={"action": "pause"})


def test_replay_stops_at_last_date(client):
    last = STATE["replay"].dates[-3]
    client.post("/api/session/replay", json={"start_date": str(last.date()), "speed": 60})
    with client.websocket_connect("/ws") as ws:
        client.post("/api/session/replay", json={"action": "play"})
        msgs = [next_tick(ws) for _ in range(3)]
        assert msgs[-1] == {"done": True}
