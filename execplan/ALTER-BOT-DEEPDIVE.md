# alter-bot-v1: Complete Probability Flow Deep Dive + All Bugs Fix

## Purpose / Big Picture

Find and fix ALL bugs in the bot's probability estimation pipeline. Previous attempts identified symptoms without finding root causes. This time: trace every line from raw weather API → bucket probability → EV → trading decision. Find every bug. Fix everything. Don't stop.

**Key symptoms to explain:**
1. Negative EV positions WINNING, positive EV LOSING — p fed into calc_ev is systematically wrong
2. bucket_prob_cumulative is defined but NEVER called — dead code
3. Sigma overrides may be making probability estimates unresponsive

## Context and Orientation

**Working directory:** `/home/alyssa/.openclaw/workspace/alter-bot-v1/`

**Key files:**
- `bot_v2.py` — main bot (~2700 lines)
- `config.json` — sigma_override, city tiers, conviction thresholds
- `data/state.json` — balance, positions, circuit breakers
- `data/city_error_history.json` — historical error data
- `data/slippage_log.jsonl` — trade log (89 entries, all won=null)

**sigma_override values from config.json:**
```
london: 6.96°C, paris: 8.2°C, hong-kong: 5.0°C, lucknow: 5.0°C,
singapore: 5.0°C, shanghai: 5.0°C, seoul: 5.0°C, tokyo: 5.0°C
```

**Default sigma:** 1.5°C

## What We Know So Far

From Turing's investigation:
1. calc_ev formula is CORRECT (p*(1-price) - (1-p)*price for YES)
2. bucket_prob_cumulative() is defined but NOT called anywhere in trading path
3. The ACTUAL probability function used is bucket_prob() — not bucket_prob_cumulative()
4. sigma_override caps sigma per city — could make probabilities too narrow or too wide

## Your Mission: Trace the Full Probability Pipeline

### Step 1: Find ALL probability calculation functions

Search for ALL functions that calculate P(temp in bucket) or P(T <= threshold):
```bash
grep -n "def bucket_prob\|def bucket_prob_cumulative\|def calc_prob\|def get_prob" bot_v2.py
```

Read EACH function. Determine:
- Which functions are actually CALLED in the trading signal path?
- Which are dead code?
- What's the difference between bucket_prob and bucket_prob_cumulative?

### Step 2: Trace the trading signal path

Find where trading decisions are made. Look for:
- Where `calc_ev` is called
- What p (probability) value is passed to it
- Where p is derived

```bash
grep -n "calc_ev\|edge\|signal\|best_side\|YES\|NO" bot_v2.py | grep -v "^.*#" | head -60
```

Read the main scan/trading loop. Key area is around line 1500-1700 (signal generation).

**Find the exact code path:**
1. Raw weather data comes in (ecmwf/hrrr/metar)
2. What transformation happens?
3. What function converts temperature → probability?
4. What function converts probability + price → EV?
5. What function converts EV → trading decision?

### Step 3: Verify bucket_prob correctness

Read `bucket_prob` function (not bucket_prob_cumulative — that's dead):
```bash
grep -n "def bucket_prob" bot_v2.py
sed -n [line-20],[line+40]p bot_v2.py
```

**Verify mathematically:**
- Input: forecast_temp, t_low, t_high, sigma
- Output: P(t_low <= T <= t_high) under N(forecast_temp, sigma²)
- Is this a valid normal CDF calculation?
- Is sigma being used correctly?

### Step 4: Check sigma_override flow

```bash
grep -n "sigma_override\|get_city_error_sigma\|sigma" config.json
grep -n "sigma_override\|get_city_error_sigma" bot_v2.py
```

**Key questions:**
- Does sigma_override ACTUALLY get used in the probability calculation?
- If sigma_override makes sigma LARGER → probabilities become LESS extreme (wider distribution)
- If sigma_override makes sigma SMALLER → probabilities become MORE extreme
- What is the EFFECT of sigma_override on the actual probabilities being calculated?

### Step 5: Check the fill_log to understand what the bot is actually doing

```bash
tail -20 data/fill_log.jsonl | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=None)) for l in sys.stdin]"
```

Look at:
- ev_used field — is it meaningful?
- side field — YES or NO?
- p (probability) field — what values is the bot using?
- Compare p to price — if p > price for YES, that's positive EV

### Step 6: Check slippage_log for probability values

```bash
tail -20 data/slippage_log.jsonl | python3 -c "import sys,json; [print(json.dumps(json.loads(l), indent=None)) for l in sys.stdin]"
```

Look at the `p` and `ev_used` fields. Are they sensible?

## The Core Hypothesis to Test

**Hypothesis:** The probability `p` fed into `calc_ev` is NOT the probability of the bucket winning. Instead, it's the probability of the temperature being IN a certain range, but the market might be asking the OPPOSITE question.

For example:
- Market: "Will temperature be >= 25°C?" (YES = T >= 25)
- bucket_prob returns P(20 <= T <= 25) — probability of temperature being IN the 20-25 range
- But calc_ev might be using P(20 <= T <= 25) as if it were P(T >= 25)

**This would cause:** Positive EV (p > price for YES) bets to LOSE because p represents the wrong event!

Verify by:
1. Find a specific market question (from fill_log or active markets)
2. Find the bucket definition (t_low, t_high)
3. Trace exactly what probability is calculated and what the market question actually is
4. Determine if there's a logical inversion

## Fixes to Apply

Once you find the bug(s), fix them:

1. **Remove dead code** — if bucket_prob_cumulative is unused, either integrate it properly or remove it
2. **Fix probability calculation** — ensure p in calc_ev represents the probability of the market resolving YES
3. **Validate sigma_override** — ensure it helps rather than hurts probability estimates
4. **Add debug logging** — add p, sigma, and bucket range to slippage_log so we can see exactly what the bot is calculating

## Validation

After any fix:
1. `python3 -m py_compile bot_v2.py` — must pass
2. `pm2 restart alter-bot-v2`
3. Check logs — confirm no errors
4. Check slippage_log for new entries — p should be a meaningful probability (0-1) that makes sense given the market question

## Don't Stop Until

- You can explain WHY negative EV positions are winning
- You can show exactly where the probability calculation is wrong
- The bug is fixed and verified
- No other bugs found in the full pipeline scan
