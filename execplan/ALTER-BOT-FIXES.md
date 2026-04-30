# Alter-Bot v2 — Structural Fixes ExecPlan

This ExecPlan is a living document. Sections `Progress`, `Surprises & Discoveries`, `Decision Log`, and `Outcomes & Retrospective` must be kept up to date as work proceeds.

Reference: ~/.openclaw/skills/execplan/references/PLANS.md

## Purpose / Big Picture

Fix three structural bugs in alter-bot-v2 that are causing balance drain and preventing profitable trades from firing:

1. **Position re-trade loop** — The same market (Atlanta Apr 26) was bet on 87+ times, burning ~$217. A deduplication guard must prevent re-betting the same market while it remains open.
2. **EV sign display bug** — NO positions show YES EV in pre-fill log, making debugging confusing.
3. **WHALE sizing** — conviction=7 always maps to SMALL_BET ($2.50). A high-conviction WHALE signal should scale up to BIG_BET.

After these fixes: Atlanta's edge can fire correctly, no more 87x re-trades, and EV logs are readable.

## Progress

- [ ] (2026-04-25 22:57 UTC+8) Milestone 1: Position deduplication guard — prevent same market re-trade
- [ ] (2026-04-25 22:57 UTC+8) Milestone 2: EV sign display fix — show correct side's EV in pre-fill log
- [ ] (2026-04-25 22:57 UTC+8) Milestone 3: WHALE sizing upgrade — conviction 7+ → BIG_BET path
- [ ] (2026-04-25 22:57 UTC+8) Milestone 4: Syntax check + validation for all changes

## Context and Orientation

**File:** `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py` (111KB, PM2 process "alter-bot-v2")

**Key sections relevant to this plan:**

- `check_market_resolved()` ~line 1540 — checks if a market is settled
- `_scan_city()` ~line 1541 — main per-city scanning logic
- `emit_observation()` ~line 2009 — emits trading signal with EV display
- `calc_kelly()` ~line 802 — Kelly fraction calculation
- `bet_size()` ~line 822 — maps Kelly to dollar amount
- `position_type` logic around conviction scoring

**State file:** `~/.openclaw/workspace/alter-bot-v1/data/state.json`
**Position storage:** In-memory `positions` list within the state dict
**Market files:** `~/.openclaw/workspace/alter-bot-v1/data/markets/*.json` (one per market)

**Key definitions:**
- `position_type`: ONE_BET / SMALL_BET / BIG_BET / NO_BET — maps conviction to bet size
- `open_positions`: markets currently held, keyed by `market_id`
- `best_signal`: the current best trade opportunity found during a scan

---

## Milestone 1: Position Deduplication Guard

### What

Before placing ANY bet, check if `market_id` already exists in `open_positions`. If it does and the market is not resolved, skip the bet and log `[HOLD] {city} {date} already held — skipping`.

### Why

Atlanta Apr 26 was filled 87 times at $2.50 = ~$217 NO bets. Polymarket shows `closed=False` so the bot thinks it's a fresh opportunity every scan. The bot accumulates the same position 87 times instead of holding one.

### Where

In `emit_observation()` around line 2009, or in the main scan loop around line 2045. The check should happen BEFORE `place_order()` is called.

### How

In the section where `best_signal` is about to be traded, add:

```python
# === DEDUP GUARD ===
# Skip if already holding this market
if best_signal["market_id"] in [p.get("market_id") for p in positions]:
    print(f"  [HOLD] {best_signal['city']} {best_signal['date']} already held — skipping")
    return new_pos, closed, dirty_markets, balance_delta
# === END DEDUP ===
```

This goes inside the block after `best_signal` is selected but BEFORE `place_order()` is called. The `positions` list is the current open positions from state.

### Validation

After applying, grep for `[HOLD]` in the code. When the bot runs, if it scans Atlanta Apr 26 again it should print `[HOLD] atlanta 2026-04-26 already held — skipping` instead of placing another order.

---

## Milestone 2: EV Sign Display Fix

### What

In the pre-fill EV display line, the sign is showing the WRONG side's EV. For a NO position, it shows YES EV (negative sign), making debugging confusing.

### Where

The EV display is in `emit_observation()` around line 2009. Look for a print statement like:

```python
print(f"  EV (pre-fill) {ev_pre:.2f} | EV (post-fill) {ev_post:.2f}")
```

### How

The issue: `calc_kelly()` is called with the correct `side` (YES/NO), but the EV displayed as `ev_pre` is calculated for the OTHER side. Fix by displaying EV for the ACTUAL side being traded.

In the signal dictionary, `best_signal["side"]` contains "YES" or "NO". Use that to display the correct EV. If the EV for the traded side is not available, compute it directly:

```python
# Show EV for the side we're actually taking, not the opposite
actual_side = best_signal["side"]
ev_for_side = edge * (1.0 / price - 1.0) if actual_side == "YES" else edge * (1.0 / price - 1.0)
# Alternative: just show the absolute edge as EV
```

The simplest correct fix: show `edge` as the EV (edge = actual expected value), not the result of `calc_kelly()` which returns a fraction.

---

## Milestone 3: WHALE Sizing Upgrade

### What

WHALE conviction (7+) always maps to SMALL_BET ($2.50). A true edge of +0.70 EV deserves BIG_BET sizing.

### Where

`position_type` assignment in `emit_observation()` or wherever conviction maps to bet size. Around line 2009 where:

```python
position_type = "NO_BET"  # default
if conviction >= 10:
    position_type = "BIG_BET"
elif conviction >= 7:
    position_type = "SMALL_BET"
```

### How

Change the thresholds so conviction 7+ upgrades to BIG_BET:

```python
if conviction >= 7:   # was 10 — WHALE conviction should size up
    position_type = "BIG_BET"
elif conviction >= 3:  # was 7 — lowered so conviction 7 still gets something above nothing
    position_type = "SMALL_BET"
```

Also verify `MAX_BET` is large enough to accommodate a $50-100 bet if balance allows. Check `bot.py` or `config.json` for `max_bet`.

---

## Milestone 4: Validation

Run these after every change:

```bash
cd /home/alyssa/.openclaw/workspace/alter-bot-v1
python3 -m py_compile bot_v2.py && echo "SYNTAX OK"
```

If syntax OK, then PM2 restart is needed to pick up changes:

```bash
pm2 restart alter-bot-v2
pm2 logs alter-bot-v2 --lines 20 --nostream
```

Expected: No `KeyError: 'source'`, no 87x re-trades, EV display shows correct sign.

---

## Decision Log

- Decision: Deduplication check goes in `emit_observation()` before `place_order()`, not inside `_scan_city()`.
  Rationale: `emit_observation()` has the complete signal context. `_scan_city()` is called per-city; deduplication is a portfolio-level concern.
  Date: 2026-04-25

- Decision: EV display fix uses `edge` directly (raw expected value) rather than trying to recompute from price.
  Rationale: `edge` is already calculated and signed correctly for the side. `calc_kelly()` returns a fraction, not EV.
  Date: 2026-04-25

- Decision: WHALE conviction threshold lowered from 10→7 for BIG_BET.
  Rationale: conviction=7 represents strong signal (auto-approve bumped from 3.5). The $2.50 SMALL_BET is inadequate for high-conviction edges.
  Date: 2026-04-25

## Surprises & Discoveries

- Polymarket `check_market_resolved()` returns `closed=False` for settled markets — this is the root cause of the re-trade loop. The bot thinks every scan is a fresh market.
- Bot has `closed=False` for Atlanta Apr 26 even after 87 fills — it never resolves the position because it never sees the market as closed.

## Outcomes & Retrospective

(In progress — to be filled after all milestones complete)
