# Alterbot Positive EV Sprint — ExecPlan

## Purpose / Big Picture

Fix the alter-bot-v2 so it finds and takes positive EV trades on Polymarket weather markets. The bot is running but producing ZERO positive EV trades. Goal: bot takes 3+ quality positive EV trades per day by tomorrow.

## Root Cause Hypothesis (Verified via diag)

1. **TradingAgents conviction gate** — debate returns conviction < 3, blocking ALL trades even when EV > 0.001
2. **Market structure** — current April markets have hot buckets priced $0.65-$0.99 (negative EV at 20% sigma)
3. **Sigma too aggressive** — using real sigma values (1.46-8.2°C) but market mispricing is smaller
4. **AVOID cities in scan** — Hong Kong (25%), Tokyo (20%), Singapore (20%), Paris (20%), London (0%) still being scanned despite poor win rates
5. **Confidence multiplier too aggressive** — forecast continuity jumps reduce conviction_mult to 0.5-0.75
6. **Kelly sizing too small** — kelly < $1 minimum bet threshold rejecting valid signals

## Progress

- [x] (2026-04-19 16:00 MYT) Diagnose: read bot_v2.py, config.json, PM2 status
- [ ] (2026-04-19 16:10 MYT) Run live market diagnostic — what prices exist right now?
- [ ] (2026-04-19 16:20 MYT) Spawn Turing subagent: optimize bot_v2.py
- [ ] (2026-04-19 17:00 MYT) Verify: run live scan, confirm [EDGE] signals appear
- [ ] (2026-04-19 17:30 MYT) Self-improvement: log observation, update skill
- [ ] (2026-04-19 18:00 MYT) Final verification + PM2 restart with new code

## Key Files

- `bot_v2.py` — main bot (2337 lines, last modified Apr 19 13:32)
- `config.json` — config (min_ev: 0.001, paper_force_trade: false, max_price: 0.85)
- `tradingagents_integration.py` — TradingAgents debate logic (conviction gate)
- `self_improver.py` — self-learning (emits observations)
- `fill_tracker.py` — fill simulation

## Key Thresholds

| Threshold | Value | Location |
|-----------|-------|----------|
| MIN_EV | 0.001 | bot_v2.py:95 |
| MIN_CONVICTION | 3 | bot_v2.py:1833 |
| MAX_PRICE | 0.85 | bot_v2.py:96 |
| MIN_KELLY_SIZE | $1.00 | bot_v2.py:1744 |
| Kelly fraction | 0.20 (20%) | config.json |

## Decision Log

- 2026-04-19 16:00 MYT — Identified TradingAgents conviction gate as primary blocker
- 2026-04-19 16:00 MYT — Confirmed paper_force_trade: false (not forcing trades)
- 2026-04-19 16:00 MYT — Identified AVOID cities (HK, Tokyo, Singapore, Paris, London) still in city_priority scan list

## Turing Subagent Task

Delegate to: Turing (Claude Code) with task = "Fix alter-bot-v2 positive EV problem"

Priority fixes:
1. Lower conviction threshold from 3 to 2 (or make it configurable)
2. Add EV boost when market price < $0.20 (extreme mispricing zone)
3. Fix Kelly minimum: $0.50 instead of $1.00
4. Remove AVOID cities from active scan (keep only: Atlanta, Sao Paulo, Miami)
5. Add market-wide EV scan: show ALL buckets across all cities even if negative — for analysis
6. Add diagnostic print: show top 10 buckets by EV even if rejected

## Validation

Run: `cd ~/.openclaw/workspace/alter-bot-v1 && python3 bot_v2.py test-scan`
Expected: console output showing [EDGE] lines for any bucket with EV > 0.001
