"""Anonymous cookie sessions held in memory. A restart clears them; single instance only."""
import time
import uuid
from dataclasses import dataclass, field

IDLE_SECONDS = 30 * 60
MAX_STRATEGIES = 6
SPEEDS = (1, 5, 20, 60)                 # trading days per second
DEFAULT_START = "2019-06-01"


@dataclass
class Session:
    sid: str
    strategies: list = field(default_factory=list)
    start_date: str = DEFAULT_START
    pos: int = 0                        # index of the current replay day in prices.index
    speed: int = 5
    playing: bool = False
    events: list = field(default_factory=list)   # ("history", id) / ("reset",), drained by the WebSocket
    conn: int = 0                       # id of the newest WebSocket; older ones stop
    last_seen: float = field(default_factory=time.time)


class SessionStore:
    def __init__(self):
        self.sessions: dict[str, Session] = {}

    def expire(self):
        cutoff = time.time() - IDLE_SECONDS
        for sid in [s for s, v in self.sessions.items() if v.last_seen < cutoff]:
            del self.sessions[sid]

    def get(self, sid: str | None) -> Session | None:
        self.expire()
        s = self.sessions.get(sid) if sid else None
        if s:
            s.last_seen = time.time()
        return s

    def create(self, start_pos: int) -> Session:
        s = Session(sid=uuid.uuid4().hex, pos=start_pos)
        self.sessions[s.sid] = s
        return s

    def add(self, s: Session, strategy_id: str) -> bool:
        if strategy_id in s.strategies or len(s.strategies) >= MAX_STRATEGIES:
            return False
        s.strategies.append(strategy_id)
        s.events.append(("history", strategy_id))
        return True

    def remove(self, s: Session, strategy_id: str):
        if strategy_id in s.strategies:
            s.strategies.remove(strategy_id)
