# SKILL.md — Review Order Flow

Review the bot's trading decisions, EV calculations, and order execution quality.

## When to Use
- Weekly or monthly audit of bot performance
- Investigating why a specific trade was or wasn't made
- Before/after config changes to validate improvement

## Review Flow

### Step 1: Get current status
```bash
cd ~/.openclaw/workspace/alter-bot-v1
python3 bot_v2.py status
```

### Step 2: Check recent fills
```bash
python3 -c "from fill_tracker import print_fill_report; print_fill_report()"
```

### Step 3: Review resolved markets
```bash
python3 bot_v2.py report 2>&1 | head -80
```

### Step 4: Check self-improvement stats
```bash
python3 self_improver.py process 2>&1 | tail -30
```

### Step 5: Review TradingAgents debate logs
```bash
ls -la data/tradingagents_logs/ | tail -10
cat data/tradingagents_logs/<recent>.json | python3 -m json.tool | head -60
```

## Key Questions
1. Are high-EV trades actually being placed?
2. Is Kelly sizing appropriate given current balance ($898.90)?
3. Are tier 1 cities (Miami, Paris, London) being prioritized?
4. Are AVOID list cities (dallas, london, paris, hong-kong, tokyo, lucknow) being skipped?
5. Is self-improvement updating sigma correctly?

## Key Metrics to Check
- **Win Rate:** Should be 90%+ on TIER 1 cities
- **EV threshold:** min_ev = 0.001 (don't trade below this)
- **Kelly fraction:** 0.20, max_bet: $5.00
- **Confidence filter:** enabled with min_conf = 0.75 for TIER 2

## Verification
```bash
python3 proper_backtest.py 2>&1 | grep -E "(win_rate|Sharpe|tier)"
python3 city_optimizer.py 2>&1 | tail -20
```

## Config Bounds (from CLAUDE.md)
- `min_tier_to_trade: 1`
- `max_tier_to_trade: 2`
- `confidence_filter.enabled: true`
- `kelly_fraction: 0.20`
- `max_bet: $5.00`
- `scan_interval: 300`
