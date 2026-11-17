"""FastAPI app: precompute every backtest once at startup, then serve replays from memory.

Run: uv run uvicorn app.main:app --reload   ->  http://localhost:8000
"""
import asyncio
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from pydantic import BaseModel

import config as C
from app.replay import Replay
from app.sessions import DEFAULT_START, SPEEDS, SessionStore
from engine.backtest import load_or_run_all
from engine.data import load_prices
from engine.metrics import scorecard
from engine.strategies import REGISTRY

STATE = {}
COOKIE = "sid"


@asynccontextmanager
async def lifespan(app: FastAPI):
    prices = load_prices()                       # cached CSV: no internet needed
    results = load_or_run_all(prices)        # precomputed at build time on Render
    STATE["replay"] = Replay(prices, results)
    STATE["store"] = SessionStore()
    STATE["strategies"] = [
        {"id": sid, "name": s["name"], "description": s["description"], "style": s["style"],
         "params": s["params"],
         "full": {k: round(v, 4) for k, v in scorecard(results[sid]).items()},
         "out_of_sample": {k: round(v, 4) for k, v in scorecard(results[sid], C.OUT_SAMPLE_START).items()}}
        for sid, s in REGISTRY.items()]
    yield


app = FastAPI(title="NSE Strategy Lab", lifespan=lifespan)


def session_for(request: Request, response: Response):
    """Existing session from the cookie, or a new one (and set the cookie)."""
    store, replay = STATE["store"], STATE["replay"]
    s = store.get(request.cookies.get(COOKIE))
    if s is None:
        s = store.create(replay.start_pos(DEFAULT_START))
        response.set_cookie(COOKIE, s.sid, httponly=True, samesite="lax", max_age=60 * 60 * 24)
    return s


def state_of(s) -> dict:
    replay = STATE["replay"]
    return {"strategies": s.strategies, "start_date": s.start_date, "speed": s.speed,
            "playing": s.playing, "current_date": str(replay.dates[s.pos].date()),
            "first_date": str(replay.dates[0].date()), "last_date": str(replay.dates[-1].date())}


@app.get("/")
def index(request: Request):
    response = FileResponse(C.ROOT / "static" / "index.html")
    session_for(request, response)
    return response


@app.get("/api/strategies")
def strategies():
    return STATE["strategies"]


class StrategyChange(BaseModel):
    add: str | None = None
    remove: str | None = None


@app.post("/api/session/strategies")
def change_strategies(body: StrategyChange, request: Request, response: Response):
    s, store = session_for(request, response), STATE["store"]
    if body.add:
        if body.add not in REGISTRY:
            raise HTTPException(404, f"unknown strategy {body.add}")
        if not store.add(s, body.add) and body.add not in s.strategies:
            raise HTTPException(400, "at most 6 strategies per session")
    if body.remove:
        store.remove(s, body.remove)
    return state_of(s)


class ReplayControl(BaseModel):
    start_date: str | None = None
    speed: int | None = None
    action: str | None = None           # play | pause | reset


@app.post("/api/session/replay")
def control_replay(body: ReplayControl, request: Request, response: Response):
    s, replay = session_for(request, response), STATE["replay"]
    if body.speed is not None:
        if body.speed not in SPEEDS:
            raise HTTPException(400, f"speed must be one of {SPEEDS}")
        s.speed = body.speed
    if body.start_date:
        s.start_date = str(replay.dates[replay.start_pos(body.start_date)].date())
    if body.start_date or body.action == "reset":
        s.pos, s.playing = replay.start_pos(s.start_date), False
        s.events.append(("reset",))
    if body.action == "play":
        s.playing = True
    elif body.action == "pause":
        s.playing = False
    return state_of(s)


@app.websocket("/ws")
async def ws(websocket: WebSocket):
    store, replay = STATE["store"], STATE["replay"]
    s = store.get(websocket.cookies.get(COOKIE))
    await websocket.accept()
    if s is None:
        await websocket.send_json({"error": "no session; reload the page"})
        await websocket.close(code=4401)
        return
    s.conn += 1                          # newest connection for this session wins
    me = s.conn
    s.events = [("reset",)]              # (re)connect: send full state from scratch
    try:
        while s.conn == me:
            s.last_seen = time.time()           # an open replay keeps the session alive
            start = replay.start_pos(s.start_date)
            while s.events:
                event = s.events.pop(0)
                if event[0] == "reset":
                    await websocket.send_json({"reset": True, "state": state_of(s),
                                               "nifty": replay.nifty_history(start, s.pos)})
                    for sid in s.strategies:
                        await websocket.send_json(replay.history(sid, start, s.pos))
                elif event[1] in s.strategies:
                    await websocket.send_json(replay.history(event[1], start, s.pos))
            if s.playing:
                if s.pos >= len(replay.dates) - 1:
                    s.playing = False
                    await websocket.send_json({"done": True})
                    continue
                s.pos += 1
                await websocket.send_json(replay.tick(s.strategies, start, s.pos))
                await asyncio.sleep(1 / s.speed)
            else:
                await asyncio.sleep(0.05)
    except WebSocketDisconnect:
        pass
