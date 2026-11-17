# NOTES.md: NSE Strategy Lab study sheet

One section per phase: the primer in plain words, what was built, and the **actual results** from the run.

---

## Phase 1: Data

### Primer
- **Index vs ETF vs futures:** NIFTY 50 (`^NSEI`) is an *index*, a number computed from 50 stock prices, and you cannot buy it directly. You trade it through an **ETF** (NIFTYBEES, a fund bought like a share) or **NIFTY futures** (a contract you can go long *or short*). Sector indices work the same way.
- **Closing prices:** one number per day. Every decision and every fill in this project happens at a close.
- **Price indices exclude dividends**, so they slightly understate what a holder earned (README limitation).
- **Alignment:** NIFTY's trading calendar is the master. Gaps of up to 3 days are forward-filled (carry the last close forward); longer gaps stay empty so no prices are invented.
- **Caching:** download once to `data/prices.csv` and commit it, so every run, test and server start uses identical numbers and works offline (reproducibility).
- **Sanity checks:** first date per ticker, missing days, and daily moves beyond ±15% (either real crashes or bad data).

### What was built
- `config.py`: every fixed setting (tickers, dates, cash rate 6%, borrow 2%, cost 0.10%, 5pp rebalance threshold, gross cap 1.0, split at 2018-01-01, ₹10,00,000 start capital).
- `engine/data.py`:
  - `download()` fetches yfinance closes and flattens yfinance's two-level `(field, ticker)` columns down to just `Close`.
  - `clean()` aligns to NIFTY trading days, repairs bad ticks, then forward-fills gaps of up to 3 days.
  - `bad_ticks()` flags a price more than 2× away from its 11-day median.
  - `load_prices()` reads the CSV cache, or downloads and saves it.
  - `checks()` builds the per-ticker check table.
  - `chart_growth()` draws Chart 1.
- Run it with `uv run python -m engine.data`, or add `--refresh` to re-download.

### Results (run on 2026-11-17)
- **All 10/10 tickers loaded.** 4,628 NIFTY trading days, 2008-01-01 → 2026-11-13. All 8 sectors loaded (6 needed).
- **Start dates differ:** NIFTY, Bank and IT start in 2008. Realty starts 2010-07-19; FMCG, Pharma and Energy start 2011-01-31; Auto and Metal start 2011-07-12. GOLDBEES starts 2009-01-02. So the sector strategies (which need 12 months of history) only have the full 8-sector universe from about mid-2012.
- **Missing days after each ticker's start (after the ≤3-day fill): 0** for every ticker.
- **Data bug found and fixed:** GOLDBEES did a 1:100 unit split in Dec 2019, and Yahoo shows 2019-12-19 and 2019-12-20 at 1/100th of the true price (−99% then +9900%). `bad_ticks()` now blanks those two days and forward-fills them. *Lesson: always look at extreme moves before trusting data.*
- **Big moves (beyond ±15%) that remain are real events:**
  - 2009-05-18: NIFTY +17.7% and Bank NIFTY +18.8%. Election result day; the market hit its upper circuit.
  - 2020-03-23: Bank NIFTY −16.7% (COVID crash).
- **Chart 1** (`reports/chart1_growth.png`, log scale, each line starts at its own first date, so lines are not directly comparable). Growth of ₹1 to 2026-11-13:

| Asset | ₹1 became | Asset | ₹1 became |
|---|---|---|---|
| NIFTY (from 2008) | 4.09 | Auto (from 2011) | 7.51 |
| Bank (from 2008) | 6.16 | Metal (from 2011) | 3.33 |
| IT (from 2008) | 6.72 | Energy (from 2011) | 4.26 |
| FMCG (from 2011) | 5.45 | Realty (from 2010) | 2.04 |
| Pharma (from 2011) | 6.08 | Gold ETF (from 2009) | 8.37 |

- What the chart shows: NIFTY fell more than 50% in 2008 and took until about 2010 to recover. March 2020 hits every index at once. Realty and Metal had long drawdowns before 2020 (good material for momentum strategies to avoid). Sectors spread far apart over time, and that spread is what sector momentum tries to capture.

---

## Phase 2: Strategies, including shorts

### Primer
- **Target weights:** a strategy doesn't place orders. It states how it wants capital split. +1.0 = all capital long, 0 = none, and whatever isn't long sits in **CASH** (CASH = 1 − sum of long weights).
- **A short** is a negative weight. −0.5 NIFTY = sold NIFTY worth half your capital without owning it: you profit if it falls and lose if it rises.
- **Shorting in India:** a cash-market short must be closed the **same day**. A multi-day short uses **NIFTY futures** (sell a contract; margin + carry) or **SLBM** (borrow the shares for a fee). The engine models it as futures-style with a 2%/year carry cost (Phase 3).
- **Gross vs net:** gross = Σ|w| = total risk taken; net = Σw = which way you lean on the market. Sector L/S is 3×(+1/6) + 3×(−1/6), so gross is 1.0 and net is 0, which makes it **market-neutral**.
- **The six strategies:** Trend (NIFTY above its 200-day average, else cash), Trend L/S (same, but −50% instead of cash), Sector momentum (top 3 sectors by 12-month return, skip negatives), Sector L/S (long top 3, short bottom 3), Vol-target (scale NIFTY down when it is jumpy, aiming for 12% vol), Buy & hold (baseline).

### What was built
- `engine/strategies.py`:
  - Six functions `f(prices, **params) -> pd.Series`, each returning weights for the **last row only**, with a `CASH` entry.
  - `REGISTRY`: id → fn, name, description, style, default params.
  - `weights_on(id, prices, date)` is the **only** way to get a decision: it slices `prices.loc[:date]` before calling the strategy. *The engine, not the strategy, controls what data is visible.*
- **Monthly strategies:** they only use prices up to the end of the **previous month**. Deciding on the last day of a month would mean knowing that tomorrow starts a new month, so they decide on the first trading day of each month and the engine fills the next day.
- **Late-starting sectors:** sector strategies use only sectors that have 12 months (252 days) of history on that date. Sector L/S needs at least 6 eligible sectors (3 long + 3 short), so it holds cash until about Feb 2012.
- `tests/test_no_lookahead.py`:
  - For every strategy and 6 dates (including 2008-10-24, 2009-03-09 and 2020-03-23), multiply every price after D by 10 and append 30 fake days. The decision at D must be identical.
  - A **"teeth" test** proves the check works: if `trend` were handed the full faked frame, its decision flips from cash to 100% NIFTY.

### Results (run on 2026-11-17)
- **`pytest`: 37 passed** (6 strategies × 6 dates + the teeth test).
- Sample decisions (made at the close of the date shown; the engine trades the next day):

| Date | trend | trend_ls | sector_mom | sector_ls | voltarget |
|---|---|---|---|---|---|
| 2009-03-02 (near the 2008–09 bottom) | cash | −0.50 NIFTY | cash (Bank/IT both down over 12m) | cash (fewer than 6 sectors) | +0.40 |
| 2020-03-23 (COVID low) | cash | −0.50 NIFTY | Bank, Realty at 1/3 each; 1/3 cash (from end-Feb ranks) | gross 1.00, net 0 | **+0.18** (vol very high) |
| 2021-06-01 (rally) | +1.00 | +1.00 | IT, Metal, Realty | long IT/Metal/Realty, short FMCG/Pharma/Energy | +0.91 |
| 2026-11-13 (latest) | +1.00 | +1.00 | Pharma, Metal; 1/3 cash | long Pharma/Metal/Energy, short IT/FMCG/Realty | +0.78 |

- What to notice:
  - At the 2020-03-23 low, trend L/S was **short** and trend was in cash, so both would miss the sharp rebound. This is the classic trend-following cost.
  - Vol-target had already cut exposure to 18%.
  - Sector L/S always has gross 1.0, net 0, and cash 0.5 (only the longs use cash).

---

## Phase 3: Backtest engine with shorts

### Primer
- **Day by day:** on day t the engine hands the strategy prices **up to t only**, gets target weights, and **fills them at t+1's close**. You can't trade at the same close you used to decide.
- **Day return** = Σ wᵢ·rᵢ + cash_w × (6%/252) − short_size × (2%/252) − 0.10% × turnover. Between trades the weights **drift** (wᵢ ← wᵢ(1+rᵢ)/(1+r_portfolio)), so winners grow as a share.
- **A short in the formula:** w = −0.5 and NIFTY −2% gives −0.5 × −2% = **+1%**. NIFTY +2% gives −1%. The borrow fee is the `− short_size × borrow_daily` term, paid every day the short is open. Short proceeds earn no cash interest (cash = 1 − longs).
- **Threshold:** trade an asset only if it is more than 5 percentage points from target.
- **Sharpe** = (mean daily return − daily cash rate) / daily volatility × √252, i.e. reward **above cash** per unit of risk. Because cash pays 6%, Sharpe values here look low; with no risk-free deduction they would look higher.
- **Max drawdown** = the worst fall from a previous peak.

### What was built
- `engine/backtest.py` → `run(strategy, prices, cost, borrow, cash_rate, threshold, gross_cap)` returns daily `equity` (starts at 1.0), daily `weights` (incl. CASH) and a `trades` list (date, side, asset, weight, price). Each day it does three things in order:
  1. earn today's return on yesterday's weights, then drift;
  2. fill yesterday's decision at today's close;
  3. decide today's target via `weights_on` (prices up to today only).
- **Trade sides:** BUY (open/add a long), SELL (reduce/close a long), SHORT (open/add a short), COVER (reduce/close a short). Flipping long→short logs SELL + SHORT.
- **Gross cap:** the target is scaled down if Σ|w| > 1.0.
- `engine/metrics.py`:
  - `scorecard()` returns annual return, volatility, Sharpe, max drawdown, worst month, and turnover (weight traded per year).
  - `running_metrics()` returns return so far, vol, Sharpe, max drawdown and current drawdown, for the replay.
- `tests/test_backtest_math.py` (on 2015–2017 data):
  - buy-and-hold at zero cost tracks NIFTY's daily returns exactly;
  - all-cash earns exactly 6%/252 a day;
  - a −100% short (zero cost/borrow, re-shorted daily) returns exactly −NIFTY's return, and with a 2% borrow it is exactly −r − 0.02/252;
  - a strategy that never trades has identical equity at 0% and 5% cost, and an empty trade list.
- `engine/report.py` → `reports/scorecard.csv`, `reports/stress.csv`, `reports/chart2_equity_drawdown.png`. One full backtest takes about 4–10 s; all six together take under a minute.

### Results (run on 2026-11-17, data to 2026-11-13)
- **`pytest`: 41 passed** (37 look-ahead + 4 maths).

**Out-of-sample scorecard (2018 → 2026-11-13), the one that counts:**

| Strategy | Ann. return | Vol | Sharpe | Max DD | Worst month | Turnover/yr |
|---|---|---|---|---|---|---|
| Trend | +7.6% | 11.4% | 0.18 | −22.5% | −6.4% | 7.85 |
| Trend L/S | +4.5% | 13.0% | −0.06 | −31.6% | −6.9% | 11.91 |
| Sector momentum | +8.4% | 18.1% | 0.21 | −37.0% | −22.4% | 4.62 |
| Sector L/S | +2.2% | 8.1% | −0.43 | **−17.6%** | −8.2% | 4.09 |
| Vol-target | +8.1% | 11.9% | 0.21 | −19.8% | −11.1% | 2.56 |
| **Buy & hold** | **+10.7%** | 16.9% | **0.33** | −38.4% | −23.2% | 0 |

**In-sample (2008–2017):**

| Strategy | Return | Sharpe | Max DD |
|---|---|---|---|
| Sector momentum | +13.2% | 0.55 | −21.4% |
| Trend | +8.4% | 0.22 | −21.2% |
| Vol-target | +7.1% | 0.13 | −21.4% |
| Buy & hold | +5.6% | 0.09 | −59.9% |
| Sector L/S | +4.9% | −0.15 | −20.5% |
| Trend L/S | +3.6% | −0.08 | −31.1% |

**Full period (2008 → 2026):** sector momentum +10.8%/yr (max DD −37.0%), trend +8.0% (−22.5%), buy & hold +7.9% (−59.9%), vol-target +7.6% (−21.4%), trend L/S +4.0% (−34.6%), sector L/S +3.6% (−20.5%).

**Stress table:**

| Strategy | 2008 | Feb–Apr 2020 | Worst DD since 2021 |
|---|---|---|---|
| Trend | +6.0%* | +0.2% | −13.8% |
| Trend L/S | +4.1%* | **+5.9%** | −16.8% |
| Sector momentum | +6.0%* | **−29.6%** | −25.6% |
| Sector L/S | +6.0%* | −3.8% | −14.6% |
| Vol-target | −15.9% | −10.7% | −17.9% |
| Buy & hold | −52.1% | −15.8% | −17.2% |

\* **Warm-up, not skill:** data starts 2008-01-01, so the 200-day average only exists from about Oct 2008, and 12-month sector returns only exist from Jan 2009. These strategies sat in cash (earning 6%) through most of the 2008 crash **because they had no signal yet**. Trend L/S's first trade was a SHORT on 2008-10-22, after NIFTY had already fallen about half. This inflates in-sample results for the trend and sector strategies and must be stated in the README. Only vol-target's 2008 number is a real test.

### What the results say (honestly)
- **Nothing beat buy-and-hold on return or Sharpe out of sample.** What the rules did buy was **smaller drawdowns**: vol-target −19.8% and trend −22.5% vs NIFTY −38.4%, while keeping about 7.5–8% a year vs 10.7%.
- **Trend L/S in 2020:** it went SHORT on 2020-02-27 (SELL 1.0 + SHORT 0.5 at 11,633), added to the short as NIFTY fell to 7,610 on 2020-03-23, and made +5.9% over Feb–Apr. Then it **stayed short through the rebound** until 2020-07-20 (COVER at 11,022 and BUY back). That is why its drawdown is −31.6%: shorts lose in V-shaped recoveries and choppy markets.
- **Trend whipsaw:** about 7.9 units of weight traded per year (145 trades). NIFTY crossing its 200-day line back and forth means buying high and selling low repeatedly, and each round trip pays costs.
- **Sector momentum** was the best in-sample (Sharpe 0.55) but halved out of sample (0.21). In Feb–Apr 2020 it held Bank and Realty, the worst-hit sectors, and lost 29.6%. Momentum ranks are a month stale in a crash.
- **Sector L/S** has the lowest volatility (8.1%) and smallest drawdown, but earned **less than cash** (2.2%/yr vs 6%), so its Sharpe is negative.
- **Resume-line candidate (true numbers):** "Out of sample, vol-targeted NIFTY had a max drawdown of −19.8% against −38.4% for NIFTY (at 8.1%/yr vs 10.7%/yr return)."

---

## Phase 4: Robustness

### Primer
- **Overfitting** = tuning a rule until it fits the past's noise. Try enough settings and one looks brilliant by luck, then disappoints on new data.
- **The test:** rerun each strategy over a grid of reasonable settings and look at **out-of-sample** results across the whole grid. Good results only at one exact setting means a fluke. A broad plateau of similar results means a robust idea.
- **The rule:** headline numbers keep the defaults chosen in advance (200-day MA; 12-month lookback, top 3; 12% target, 20-day window), **even if another cell looks better**. Picking the best cell after seeing 2018+ data would turn the out-of-sample period into an in-sample one.

### What was built
- `engine/sensitivity.py`: backtests each setting on the full history, measures Sharpe, max drawdown and return on **2018 onward only**, and saves `reports/sensitivity.csv` (29 settings, defaults marked `*`).
  - Trend MA length: 50, 100, 150, 200, 250.
  - Sector momentum lookback: 3/6/9/12 months (63/126/189/252 days) × top 2/3/4.
  - Vol-target: 8/10/12/15% × window 10/20/60 days.
- **Consistency check:** the default cells reproduce Phase 3's out-of-sample numbers exactly (trend 0.18 / −22.5%, sector_mom 0.21 / −37.0%, voltarget 0.21 / −19.8%).

### Results (run on 2026-11-17), out-of-sample 2018 → 2026-11-13. NIFTY buy & hold for reference: Sharpe 0.33, max DD −38.4%.

**Trend (MA length):**

| MA | 50 | 100 | 150 | **200*** | 250 |
|---|---|---|---|---|---|
| Sharpe | 0.22 | 0.23 | 0.17 | **0.18** | 0.11 |
| Max DD | −17.1% | −17.2% | −17.8% | **−22.5%** | −19.8% |

**Sector momentum: Sharpe (rows = lookback days, cols = top N):**

| lookback | top 2 | top 3 | top 4 |
|---|---|---|---|
| 63 (3m) | 0.42 | 0.46 | 0.49 |
| 126 (6m) | 0.02 | 0.07 | 0.10 |
| 189 (9m) | 0.18 | 0.37 | 0.29 |
| **252 (12m)** | −0.07 | **0.21*** | 0.26 |

**Sector momentum: max drawdown:**

| lookback | top 2 | top 3 | top 4 |
|---|---|---|---|
| 63 | −38.9% | −27.9% | −22.1% |
| 126 | −57.2% | −48.8% | −40.1% |
| 189 | −32.9% | −26.7% | −28.7% |
| **252** | −53.3% | **−37.0%*** | −30.1% |

**Vol-target: Sharpe / max DD (rows = target, cols = window):**

| target | 10 | 20 | 60 |
|---|---|---|---|
| 8% | 0.19 / −13.7% | 0.23 / −13.7% | 0.19 / −18.4% |
| 10% | 0.24 / −16.2% | 0.21 / −17.3% | 0.19 / −21.7% |
| **12%** | 0.27 / −18.4% | **0.21 / −19.8%*** | 0.19 / −25.4% |
| 15% | 0.29 / −20.9% | 0.29 / −23.9% | 0.24 / −29.3% |

### What the grid says about overfitting
- **Trend is robust in its drawdown benefit.** Every MA from 50 to 250 had max DD between −17% and −22.5% (vs −38.4% for NIFTY), and Sharpe stayed in a narrow 0.11–0.23 band. The default 200 is middle of the pack, not the best cell.
- **Vol-target is the most robust.** Results change smoothly and predictably: a lower target gives a lower drawdown in every column (8% → about −14%, 15% → about −21 to −29%), and every cell beats NIFTY's −38.4%. The drawdown control comes from the *idea* (cut exposure when volatility spikes), not a lucky number.
- **Sector momentum is fragile.** Sharpe jumps around with lookback in no orderly pattern (3m: 0.46, 6m: 0.07, 9m: 0.37, 12m: 0.21) and drawdowns range from −22% to −57%. When neighbouring settings disagree this much, any single result is mostly noise. Top 2 is almost always worst (too concentrated).
- **Temptation not taken:** 3-month momentum, top 4, looks best (0.49). Switching to it now would be exactly the overfitting this phase guards against. **Defaults stay unchanged.**
- **Interview answer (Q11):** "The grid shows which results are structural. Vol-targeting and trend cut drawdowns across every setting I tried, so I trust that. Sector momentum's results swing wildly between neighbouring lookbacks, so I treat its headline number as unreliable, and I didn't switch to the best-looking cell because that would be tuning on the test set."

---

## Phase 5: Backend (precompute, sessions, replay)

### Primer
- **REST vs WebSocket:** REST = ask-and-answer, one reply per request. A **WebSocket** is a connection that stays open, so the server can **push** a tick every 1/speed seconds. Polling REST 60×/s would be 60 full HTTP requests per user per second.
- **Precompute:** backtests are deterministic, so all six run **once at startup** and stay in memory. A replay only **reads slices**, so 100 users cost about as much as 1.
- **Cookie sessions:** the first visit gets a random UUID in a `sid` cookie, which the browser sends back on every request *and* on the WebSocket. **Not IP-based:** many people share one IP (college Wi-Fi, mobile carrier NAT) and one person's IP changes, so IP would mix users up. IP is only good for rate limiting.
- **A replay is a cursor:** start date + current position + speed + playing flag. Each tick moves one trading day forward and sends that day's slice, rebased to ₹10,00,000 at the session's start.
- **Expiry:** sessions idle for 30 minutes are deleted.

### What was built
- `app/main.py`:
  - **Startup:** load the cached CSV (no internet), `run_all` (6 backtests in **parallel processes**, about 14.5 s), build the replay and the strategy list with full and out-of-sample scorecards.
  - `GET /` serves the page and sets the `sid` cookie (httponly, samesite=lax).
  - `GET /api/strategies` returns the registry and scorecards.
  - `POST /api/session/strategies {add|remove}` (max 6).
  - `POST /api/session/replay {start_date, speed ∈ 1/5/20/60, action: play|pause|reset}`; a new start date also resets.
  - `WS /ws` reads the cookie. On connect it sends `{reset, state, nifty history}` plus each selected strategy's history. While playing it sends one tick, then sleeps 1/speed s. At the last date it sends `{"done": true}`.
- **How REST and the WebSocket talk:** REST calls only change session state and push events (`("history", id)`, `("reset",)`) onto the session. The WebSocket loop drains those events. **Mid-replay add** therefore sends that strategy's history from the start date to now in one message, then includes it in later ticks. **Remove** simply drops it from the next tick.
- **Two tabs on one cookie** share a session, and the **newest WebSocket wins** (older loops stop), so the replay doesn't advance twice as fast.
- `app/replay.py`: `Replay` holds the precomputed results and trades grouped by date, and builds ticks in the plan's format. Running Sharpe and vol are `null` until 20 days have passed (annualising 5 days gave a meaningless "Sharpe 8.17").
- `app/sessions.py`: `Session` dataclass and `SessionStore` (in-memory dict, 30-minute idle expiry, 6-strategy cap).
- `tests/test_replay.py`, using FastAPI's `TestClient`:
  - the `/` cookie is set and `/api/strategies` lists all 6;
  - add trend_ls and buy_hold, play from 2020-03-02 at 60×: 5 ticks have increasing dates and **equity matches the precomputed backtest to the paisa**;
  - after removing buy_hold it is gone within one tick;
  - a replay started 2 days before the end ends with `{"done": true}`.
- `static/index.html` is a placeholder until Phase 6.

### Results (run on 2026-11-17)
- **`pytest`: 44 passed** (37 look-ahead + 4 maths + 3 replay), about 20 s.
- **Startup precompute: 14.5 s** in parallel (about 45 s sequential). **One tick for all 6 strategies: about 9 ms**, nearly all of it running metrics over the slice so far. That is well under the 16 ms budget at 60 days/s.
- **Live server demo** (a real WebSocket client, start 2020-03-16, trend_ls + buy_hold, ₹10,00,000 each):

| Date | NIFTY day | Trend L/S | Buy & hold |
|---|---|---|---|
| 2020-03-17 | −2.50% | ₹10,11,965 (+1.20%) | ₹9,74,955 |
| 2020-03-18 | −5.56% | ₹10,37,530 (+2.53%) | ₹9,20,782 |
| 2020-03-20 | +5.83% | ₹10,20,999 (−2.79%) | ₹9,50,861 |
| **2020-03-23** | **−12.98%** | **₹10,90,658 (+6.82%)** | **₹8,27,435** |
| 2020-03-25 | +6.62% | ₹10,40,306 (−3.43%) | ₹9,04,370 |

- 2020-03-23 tick for trend_ls: `positions {^NSEI: −0.5, CASH: 1.0}`, gross 0.5, net −0.5, `trades_today [SHORT ^NSEI 0.0726]`. The short had shrunk below 0.5 as NIFTY fell, so the engine **added to the short** to get back to −0.5. Note the rebound days (03-20, 03-25): the short loses whenever NIFTY bounces.
- Adding voltarget mid-replay sent a backfill of 8 days (2020-03-16 → 2020-03-25), and the next tick (03-26) contained all three strategies.

---

## Phase 6: The single page

### Primer
- **One file, no build step:** `static/index.html` holds the HTML, CSS and plain JS. Chart.js 4.4.1 comes from cdnjs, and FastAPI serves the file.
- **The page mirrors the server:** buttons send REST calls that change the *server's* session, and the page redraws from what the server returns. So a reload or a second tab shows the same replay (the cookie identifies the session).
- **Four WebSocket messages drive everything:**
  - `reset` clears the page and loads NIFTY from the start date;
  - `history` adds one strategy's curve so far;
  - `tick` appends one day everywhere;
  - `done` means the replay reached the last date.
- **Smooth at 60 days/s:** ticks only change data, the screen redraws at most once per frame (`requestAnimationFrame`), and Chart.js animation is off.
- **Reconnect:** if the socket drops, the page retries after 1 s, 2 s, 4 s, up to 10 s. If the session expired, one REST call issues a fresh cookie first.

### What was built (`static/index.html`)
- **Header:** title; amber **"Historical replay — not live trading"** badge; start date picker (default 2019-06-01); Play/Pause, Reset, speed 1×/5×/20×/60×; current replay date and connection status.
- **Left panel:** 6 strategy cards showing a fixed colour per strategy, name, style tag, description, **out-of-sample Sharpe** and an Add/Remove button.
- **Equity chart:** selected strategies plus NIFTY rebased to ₹10,00,000 (dashed), updating every tick.
- **Running metrics table:** equity, day return, return so far, Sharpe ("—" for the first 20 days), max drawdown, current drawdown, gross and net.
- **Positions:** per strategy, a bar per asset centred on zero (**green = long to the right, red = short to the left**), with gross, net and cash %.
- **Trades feed:** newest first; BUY green, SHORT red, SELL and COVER muted versions; with date, strategy and asset.
- **Footer:** data source and assumptions, "not live market data, not investment advice".
- **Phone layout:** panels stack in one column below 900 px wide.

### Results (checked 2026-11-17 in headless Edge via Playwright)
- **The browser test** (a scratchpad script, not part of the repo):
  - added trend_ls, sector_ls, voltarget and buy_hold, played at 60× from 2019-06-01 and paused at 2020-03-27;
  - every chart series had the same 202 days;
  - removing sector_ls and adding trend mid-replay kept all series aligned (backfill works);
  - **a reload restored the same replay date and strategies** from the cookie;
  - phone width (390 px): no horizontal scroll;
  - **0 console errors** after the fixes below.
- **Fixed after looking at the screenshots:** the NIFTY reference line was the same grey as buy & hold and hid under it (now lighter and thinner); x-axis dates overlapped on a phone (now 4 ticks); and the browser's automatic `/favicon.ico` request returned 404 (an empty favicon link stops it).
- Screenshot saved as `reports/dashboard.png`. **Replay from 2019-06-01 to 2020-03-27** (₹10,00,000 each):

| Strategy | Equity | Return | Max DD | Positions on 2020-03-27 |
|---|---|---|---|---|
| Sector long/short | ₹10,28,449 | +2.8% | −4.4% | long Bank/FMCG/Realty, short Pharma/Auto/Metal; gross 0.89, net +0.06 |
| Trend long/short | ₹10,06,243 | +0.6% | −14.2% | NIFTY −53% (short) |
| Vol-target | ₹8,41,803 | −15.8% | −19.8% | NIFTY +19% |
| Buy & hold | ₹7,16,401 | −28.4% | −38.4% | NIFTY +100% |

- **What to say in a demo:** through the COVID crash the market-neutral sector book barely moved (max DD −4.4% vs −38.4%), and trend L/S had flipped short in late Feb and finished the crash flat. Vol-target's −19.8% and NIFTY's −38.4% here are **the same** as their full out-of-sample max drawdowns: the worst drawdown of 2018–2026 for both happened in this window.

---

## Phase 7: README and deploy

### Deploy decision: Render, not Vercel (2026-11-17)
- Vercel now supports FastAPI WebSockets, but three of its rules clash with this design:
  1. a REST call and a WebSocket are **not guaranteed to hit the same instance**, and Vercel says not to keep state in memory;
  2. on Hobby, WebSockets are **cut after 5 minutes**;
  3. every new instance would redo the startup precompute.
- Options were: controls over the WebSocket only, a Redis session store, or Render. **Chose Render:** one always-on instance, so the plan's in-memory cookie sessions and long WebSockets work unchanged.
- **Interview angle:** "Serverless platforms scale by running many short-lived copies, so in-memory sessions break. My design assumes one long-running instance, which is why it deploys to Render. To scale out I'd move sessions to Redis."

### Changes for Render's free tier (512 MB RAM, small CPU share)
- Startup used to run the 6 backtests in 6 parallel processes, which would exceed 512 MB.
- Now the **build step** (`python -m engine.backtest`) computes them once into `data/results.pkl` (3.2 MB, git-ignored), and startup only loads it.
- The file stores a **fingerprint** (a hash of `prices.csv`, `config.py` and `engine/*.py`). If the data or engine code changes, results are recomputed instead of serving stale numbers.
- Measured locally: first build 13.2 s, reload 0.1 s, **server startup to first response 5.8 s, memory 141 MB**.
- `render.yaml` (Blueprint):
  - build: `pip install uv && uv sync --frozen && uv run --frozen python -m engine.backtest`;
  - start: `uvicorn app.main:app --host 0.0.0.0 --port $PORT --forwarded-allow-ips "*"`;
  - health check: `/api/strategies`; Python 3.12.8; free plan; single instance.

### README
- Written from the actual run outputs (`reports/scorecard.csv`, `reports/stress.csv`, `reports/sensitivity.csv`, `reports/dashboard.png`). Includes the 3-sentence summary, an architecture diagram (mermaid), strategy table, scorecards, stress table with the 2008 warm-up asterisk, robustness grids, how to run, tests and limitations.

### Resume bullets (filled from the actual run)
- Built a Python backtesting engine for NSE long/short strategies (trend, sector momentum, market-neutral, volatility targeting) with next-day execution, costs, short-borrow fees and unit tests enforcing no look-ahead bias; best out-of-sample (2018–2026) max drawdown −17.6% (market-neutral sector L/S) vs −38.4% for NIFTY, and −19.8% for vol-targeted NIFTY while earning 8.1%/yr.
- Shipped a FastAPI + WebSocket single-page dashboard that replays strategies day by day with live-updating equity, long/short positions, trades and risk metrics, serving per-user cookie sessions from precomputed results.

### 60-second explanation, blanks filled
> "…Out of sample, vol-targeted NIFTY had a max drawdown of −19.8% against −38.4% for NIFTY, while returning 8.1% a year vs 10.7%."

### Live deploy (2026-11-17)
- **URL:** https://nse-strategy-lab-c9z7.onrender.com/ (repo: https://github.com/singhsrj/nse-strategy-lab)
- **Checked live:**
  - `/api/strategies` out-of-sample scorecards are **identical** to the local run;
  - `/` sets the `sid` cookie (HttpOnly, SameSite=Lax);
  - the headless-browser test passed over `wss://`: 4 strategies played at 60× to 2020-03-31, all series 204 days, remove/add mid-replay aligned, the replay survived a page reload, no horizontal scroll on a phone, 0 console errors.
- **Before a demo:** open the URL a minute early. The free tier sleeps when idle, and waking it takes up to about a minute (sessions reset on wake).
