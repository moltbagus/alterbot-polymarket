# Persist kelly_size to state.json and emit to self_improver tracker

## Purpose / Big Picture

The bot calculates `kelly_size` (the Kelly-derived bet size in dollars) but never persists it to the position or emits it to the self-improvement tracker. We need to capture `kelly_size` at entry time, store it in the position (state.json), and emit it via `_tracker.add_error()` so the self-improver has full PnL attribution data.

## Context and Orientation

File: `alter-bot-v1/bot_v2.py`

Key positions where `kelly_size` must flow:
1. **Line ~2147-2148** — `best_signal` dict is built; `kelly` is stored but NOT `kelly_size`
2. **Lines ~2116-2122** — `kelly` calculated and `size` derived; `size` IS the kelly_size
3. **open_position() / state.json** — position dict written; `kelly_size` field absent
4. **_tracker.add_error() call (line ~2639)** — `position_size=pos.get("cost")` passed but `kelly_size` field not emitted

`kelly_size` = the dollar amount `bet_size(kelly, balance)` at entry time (BEFORE conviction multiplier). This is the baseline Kelly bet, used to compute whether conviction overrode Kelly and by how much.

## Progress

- [ ] (2026-04-30 11:50 MYT) Write ExecPlan
- [ ] (pending) Spawn Turing with ExecPlan to implement
- [ ] (pending) Verify: check state.json positions have kelly_size, observation emit has kelly_size

## Decision Log

- Decision: Store raw Kelly bet size BEFORE conviction multiplier
  Rationale: Conviction multiplier is an override — we want to track both the Kelly baseline and the actual size to see when conviction causes oversized bets.
  Date: 2026-04-30 / TIGER001

## Plan of Work

### Step 1: Add `kelly_size` to `best_signal` dict

In `best_signal` dict (around line 2147), after `"kelly": round(kelly, 4)` add:

```
"kelly_size":   round(size, 2),   # Kelly-derived bet $ BEFORE conviction multiplier
```

Note: At this point `size` is the Kelly bet BEFORE conviction amplification. Store this raw value. The conviction-amplified `size` is the actual bet but we need both for attribution.

### Step 2: Ensure `open_position()` stores `kelly_size`

Find where `open_position()` is called (around line 2203). The `best_signal` dict is passed in. Verify `kelly_size` is included in what gets persisted. If `open_position()` uses explicit field list, add `kelly_size` to that list.

### Step 3: Emit `kelly_size` in `_tracker.add_error()`

In `_tracker.add_error()` call (around line 2639), add:
```
kelly_size=pos.get("kelly_size"),
```

The existing `position_size=pos.get("cost")` is the actual bet $. `kelly_size` is the Kelly baseline for comparison.

### Step 4: Verify `state.json` persistence

After a trade executes, `state.json` positions should have a `kelly_size` field. Check after next trade resolves.

## Concrete Steps

After implementing, verify with:
```bash
cd ~/.openclaw/workspace/alter-bot-v1
python3 -c "import json; state=json.load(open('data/state.json')); [print(p['market_id'], p.get('kelly_size'), p.get('cost')) for p in state.get('positions',[]) if 'kelly_size' in p]"
```

Expected: positions with `kelly_size` field showing dollar value.

For observation emit, verify in logs after a resolve cycle:
```
[tracker] emit: kelly_size=X.XX ...
```

## Validation and Acceptance

1. A trade that triggers Kelly signal shows `kelly_size` in `state.json` position after opening
2. After resolving, `_tracker.add_error()` is called with `kelly_size` kwarg
3. No new errors or regressions in trade execution

## Idempotence and Recovery

This is a pure additive field addition. No existing fields are modified or removed. Safe to run multiple times. If state.json already has positions without `kelly_size`, that's fine — only new positions will have it. Backward-compatible.
