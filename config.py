"""All fixed settings in one place. Never tune these on 2018+ data."""
from pathlib import Path

ROOT = Path(__file__).parent
DATA_DIR = ROOT / "data"
REPORTS_DIR = ROOT / "reports"
PRICES_CSV = DATA_DIR / "prices.csv"

START_DATE = "2008-01-01"

# Market index and the sector indices. Ones that fail to load are dropped (need >= 6 sectors).
NIFTY = "^NSEI"
SECTORS = [
    "^NSEBANK", "^CNXIT", "^CNXFMCG", "^CNXPHARMA",
    "^CNXAUTO", "^CNXMETAL", "^CNXENERGY", "^CNXREALTY",
]
GOLD = "GOLDBEES.NS"
TICKERS = [NIFTY] + SECTORS + [GOLD]
MIN_SECTORS = 6

# Data cleaning
MAX_FFILL_DAYS = 3        # forward-fill gaps of up to this many trading days
BIG_MOVE = 0.15           # flag daily moves beyond +/-15%

# Engine assumptions (used from Phase 3)
CASH_RATE = 0.06          # cash earns 6% a year
BORROW_RATE = 0.02        # shorts pay 2% a year on their size
COST = 0.001              # 0.10% of traded value
REBALANCE_THRESHOLD = 0.05
GROSS_CAP = 1.0
TRADING_DAYS = 252

# Research split
IN_SAMPLE_END = "2017-12-31"
OUT_SAMPLE_START = "2018-01-01"

START_CAPITAL = 1_000_000  # Rs 10,00,000
