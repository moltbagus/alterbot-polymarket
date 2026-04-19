# Alter-Bot Optimization Execution Plan

## Context
Colbert wants the alter-bot to become the best Polymarket trading bot. Current status:
- Balance: $26,426.82
- Running: 17min uptime, no new errors
- Error log is stale (old KeyError from pre-fix code)
- Net PnL this week: +$1,446.15 from 9 closed trades
- Problem: Bot is not finding [EDGE] signals for current markets

## Goals (Priority Order)

### P0 - Fix & Stabilize
1. Verify no runtime errors (the KeyError is from stale log, not current code)
2. Ensure bot restarts cleanly with `--update-env`
3. Verify self-improvement observations are being emitted

### P1 - Code Quality
1. Remove dead code (unused imports, functions, variables)
2. Audit bot_v2.py for bloat — keep only what the trading logic needs
3. Verify `simulate_fill` properly handles partial fills
4. Clean up `last_scan_time` persistence
5. Remove duplicate/conflicting logic paths

### P2 - Trading Logic
1. Analyze why [EDGE] signals aren't appearing (EV < 0.001 threshold issue)
2. Review min_ev threshold — is 0.001 too high for current market conditions?
3. Check if whale filters are truly disabled (already done: whale_strategies.enabled: false)
4. Review city scanning — are we scanning the right cities at the right times?
5. Check if paper_force_trade should be used to bypass RiskManager

### P3 - Self-Improvement
1. Verify self_improver.py is emitting observations to memory/
2. Check if city_error_history.json is being updated correctly
3. Ensure calibration auto-reload is working (seen [BIAS-RELOAD] in logs)
4. Verify sigma/bias corrections are applied in trading decisions

### P4 - Polymarket API / Data
1. Verify market data freshness (are we getting new data on each scan?)
2. Check if API rate limiting is affecting scans
3. Audit fill simulation accuracy vs real fills

## Bot Architecture
- Main: bot_v2.py (PM2: alter-bot-v2)
- TradingAgents: tradingagents_integration.py
- Fill simulation: fill_tracker.py
- Self-improvement: self_improver.py
- Config: config.json (DO NOT CHANGE)

## Key Files
- bot_v2.py: Main scan/trade loop (~2300 lines)
- tradingagents_integration.py: Debate logic (~1089 lines)
- fill_tracker.py: Fill simulation (~400 lines)
- self_improver.py: Calibration system (~600 lines)
- config.json: Configuration (DO NOT EDIT)

## Working Directory
`/home/alyssa/.openclaw/workspace/alter-bot-v1/`

## Commands
- PM2 restart: `pm2 restart alter-bot-v2 --update-env`
- PM2 logs: `pm2 logs alter-bot-v2 --nostream --lines 100`
- Bot balance: Check state.json or PM2 logs for "balance: $X"

## Success Metrics
1. Bot uptime > 1 hour without restarts
2. [EDGE] signals appearing and executing trades
3. Balance growing (more wins than losses)
4. Self-improvement observations being logged
5. No crashes or KeyErrors in current session
