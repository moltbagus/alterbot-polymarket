# alter-bot-v1: calc_ev Formula Fix + Remaining P0 Bugs

This ExecPlan is a living document. Follow `~/.openclaw/skills/pua/SKILL.md` methodology — reproduce→localize→fix→guard before claiming done. Owner: TIGER001, delegated to Turing.

## Purpose / Big Picture

The bot's EV calculation is WRONG. It uses `p - price` which is NOT expected value — it's just the raw probability minus price (a meaningless number for trading). The correct Kelly-based EV for a YES bet is `p*(1-price) - (1-p)*price`. This miscalibration causes the bot to take bad trades and miss good ones, directly contributing to the 31% win rate.

After fix: all fill_log EV values will reflect true expected value, and the bot will make better sizing decisions.

## Progress

- [ ] (2026-04-29 05:37 MYT) Find and fix calc_ev in bot_v2.py — replace `p - price` with correct formula
- [ ] (2026-04-29 05:37 MYT) Verify fix with 3 test cases (manual calculation)
- [ ] (2026-04-29 05:37 MYT) Add ev_used to slippage_log output (was showing `ev_used=?`)
- [ ] (2026-04-29 05:37 MYT) Run py_compile, restart bot, confirm no errors
- [ ] (2026-04-29 05:37 MYT) Check fill_log for correct EV values post-fix

## Context and Orientation

**Files:**
- `alter-bot-v1/bot_v2.py` — main bot, contains `calc_ev` function
- `alter-bot-v1/config.json` — city tiers, conviction thresholds
- `alter-bot-v1/data/state.json` — balance, positions, circuit breakers
- `alter-bot-v1/data/fill_log.jsonl` — trade log with EV column

**calc_ev current implementation (WRONG):**
The function uses `p - price` as expected value. This is not EV — it's just probability minus price, which has no financial meaning.

**calc_ev correct formula:**
For a YES position (betting that event resolves YES):
```
EV = p * (1 - price) - (1 - p) * price
```
Where:
- p = your estimated probability (e.g., 0.73 for 73%)
- price = cost of the YES position (e.g., 0.65 means you pay $0.65 to buy)

Example: p=0.73, price=0.65
- Wrong (current): 0.73 - 0.65 = 0.08 (nonsense)
- Correct: 0.73 * (1 - 0.65) - 0.27 * 0.65 = 0.73*0.35 - 0.27*0.65 = 0.2555 - 0.1755 = 0.08

For a NO position (betting that event resolves NO):
```
EV = (1 - p) * price - p * (1 - price)
```

## Plan of Work

### Step 1: Find calc_ev function

```bash
grep -n "def calc_ev\|calc_ev" alter-bot-v1/bot_v2.py | head -30
```

Read the full function — typically around line 400-600. Show the actual code.

### Step 2: Replace with correct formula

Find `p - price` in the EV calculation. Replace with:
```python
# For YES position:
ev = p * (1 - price) - (1 - p) * price

# For NO position (if applicable):
# ev = (1 - p) * price - p * (1 - price)
```

If the function has separate branches for YES/NO, handle each correctly.

### Step 3: Verify with 3 test cases

Manually calculate expected values:

Test case 1: p=0.73, price=0.65 (YES)
- Expected EV: 0.73*(1-0.65) - 0.27*0.65 = 0.2555 - 0.1755 = **0.08**

Test case 2: p=0.41, price=0.40 (YES)
- Expected EV: 0.41*(1-0.40) - 0.59*0.40 = 0.246 - 0.236 = **0.01**

Test case 3: p=0.25, price=0.30 (YES)
- Expected EV: 0.25*(1-0.30) - 0.75*0.30 = 0.175 - 0.225 = **-0.05** (bad bet)

After fix, run the function with these values and confirm output matches.

### Step 4: Add ev_used to slippage_log

Search for slippage_log output:
```bash
grep -n "slippage_log\|ev_used" alter-bot-v1/bot_v2.py
```

The `ev_used=?` means the variable is being referenced but not assigned. Find where it should be set (from calc_ev result) and ensure it's written to slippage_log.

### Step 5: Verify + restart

```bash
python3 -m py_compile alter-bot-v1/bot_v2.py && echo "SYNTAX OK"
pm2 restart alter-bot-v2
pm2 logs alter-bot-v2 --lines 30 --nostream
```

## Validation and Acceptance

1. `calc_ev(0.73, 0.65)` returns **0.08** (not 0.08 from `p - price` coincidentally — test the actual formula logic)
2. `calc_ev(0.41, 0.40)` returns **0.01**
3. `calc_ev(0.25, 0.30)` returns **-0.05**
4. Slippage log entries now show `ev_used=0.XX` not `ev_used=?`
5. Bot restarts without error

## Decision Log

- Decision: Fix calc_ev formula first before other issues
  Rationale: Wrong EV → wrong position sizing → compounding losses. Highest leverage fix.
  Date/Author: 2026-04-29 / TIGER001

## Surprises & Discoveries

TBD

## Outcomes & Retrospective

TBD
