# alter-bot-v1: Tier Configuration & Balance Display Fixes

This ExecPlan is a living document. The sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Reference: `~/.openclaw/skills/execplan/references/PLANS.md` — follow PLANS.md to the letter.

## Purpose / Big Picture

The bot is running but opening ZERO new trades because only 2 cities (Atlanta + Miami) pass the tier filter, and both already have open positions. We need to:
1. Widen the tier aperture so Ankara (tier 3, has today's market) can be scanned
2. Show the correct balance from state.json at startup instead of hardcoded $1,000

After this change, the bot should be able to open new positions in Ankara and other tier 3 cities that have markets today.

## Progress

- [ ] (2026-04-29 05:30 MYT) Increase MAX_TIER from 2 → 3 in config.json or bot_v2.py
- [ ] (2026-04-29 05:30 MYT) Verify Ankara is in tier list and not on circuit-break avoid list
- [ ] (2026-04-29 05:30 MYT) Fix balance display: load from state.json at startup, not hardcoded $1,000
- [ ] (2026-04-29 05:30 MYT) Restart bot, verify no errors, confirm balance shows $654.89
- [ ] (2026-04-29 05:30 MYT) Confirm bot scans Ankara after restart

## Context and Orientation

Key files:
- `alter-bot-v1/bot_v2.py` — main bot logic
- `alter-bot-v1/config.json` — MAX_TIER setting, tier city assignments
- `alter-bot-v1/data/state.json` — persistent state including balance

Key terms:
- `MAX_TIER` — maximum tier level the bot will scan (currently 2, means only tier 1 + tier 2 cities)
- `tier_3` — cities one tier below the scan threshold; Ankara is tier 3 but has a live market
- `circuit_broken` — cities permanently excluded due to poor win rate (dallas 0%, london 0%, etc.)

Current tier assignment (from debug report):
- Tier 1: Atlanta (73% WR), Sao Paulo (60% WR)
- Tier 2: Miami (41% WR)
- Tier 3: Ankara and others
- Avoid: dallas, london, lucknow, tokyo, paris, hong-kong, sao-paulo, seoul, singapore, nyc, toronto, buenos-aires, wellington, tel-aviv, munich, seattle, chicago

## Plan of Work

### Step 1: Increase MAX_TIER to 3

Find where MAX_TIER is defined. It may be in config.json or hardcoded in bot_v2.py. Change value from 2 to 3.

If in config.json:
```json
"MAX_TIER": 3
```

If hardcoded in bot_v2.py, find and change:
```python
MAX_TIER = 3  # was 2
```

### Step 2: Verify Ankara is NOT on circuit-break list

Check that Ankara is not in the `circuit_broken` list in state.json or in the `avoid` list in config.json. The debug report says Ankara has an active market for 2026-04-28 — confirm it's scannable.

### Step 3: Fix balance display at startup

In bot_v2.py, find the startup sequence where `balance = 1000` (hardcoded default). Replace with loading from state.json:

```python
# Load balance from state.json if it exists
state_path = Path("data/state.json")
if state_path.exists():
    with open(state_path) as f:
        state = json.load(f)
        balance = state.get("balance", 1000)
else:
    balance = 1000
```

Ensure this runs AFTER state.json is loaded, not before.

### Step 4: Restart and validate

After changes:
1. Run `pm2 restart alter-bot-v2`
2. Check startup log for balance display (should show ~$654.89 not $1,000)
3. Wait 5 minutes, check for new scan activity
4. Confirm Ankara appears in scan output

## Concrete Steps

```bash
# 1. Read current config
cat alter-bot-v1/config.json | grep -A5 "MAX_TIER\|tier"

# 2. Read current state balance
cat alter-bot-v1/data/state.json | grep balance

# 3. Find MAX_TIER in bot_v2.py
grep -n "MAX_TIER" alter-bot-v1/bot_v2.py

# 4. Find balance initialization in bot_v2.py
grep -n "balance.*1000\|1000.*balance" alter-bot-v1/bot_v2.py

# 5. Restart bot
pm2 restart alter-bot-v2

# 6. Check startup output
pm2 logs alter-bot-v2 --lines 50 --nostream
```

## Validation and Acceptance

1. Bot restarts without error
2. Startup log shows balance ~$654.89 (from state.json), NOT $1,000
3. Bot begins scanning Ankara (tier 3 city with today's market)
4. No new error loops in pm2 logs

## Decision Log

- Decision: Increase MAX_TIER from 2 to 3
  Rationale: Ankara (tier 3) has a live market for today but is blocked. Widen aperture to allow tier 3 scanning.
  Date/Author: 2026-04-29 / TIGER001

- Decision: Load balance from state.json at startup
  Rationale: Hardcoded $1,000 is misleading — actual balance is $654.89. Must read from persistent state.
  Date/Author: 2026-04-29 / TIGER001

## Surprises & Discoveries

- (From debug report) The bot was running fine but just couldn't find any new markets to trade because only 2 cities passed the tier filter, both with open positions
- 17 cities on avoid list — very restrictive. Sao-paulo is on avoid list but was tier 1 with 60% WR. Possible future task: review avoid list criteria.

## Outcomes & Retrospective

TBD — plan only, not yet executed.
