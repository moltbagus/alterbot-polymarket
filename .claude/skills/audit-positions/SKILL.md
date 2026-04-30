# SKILL.md — Audit Positions

Audit open positions, portfolio health, and risk exposure in alter-bot-v1.

## When to Use
- Before bot restart
- After large market move
- Weekly risk review

## Audit Flow

### Step 1: Get open positions
```bash
cd ~/.openclaw/workspace/alter-bot-v1
python3 bot_v2.py status
```

### Step 2: Check portfolio health
```bash
python3 -c "from self_improver import check_portfolio_health; check_portfolio_health()"
```

### Step 3: Review state file
```bash
cat data/state.json | python3 -m json.tool | head -50
```

### Step 4: Check recent observations
```bash
ls -la memory/self-improvement/observations/ | tail -5
```

### Step 5: Check balance trajectory
```bash
cat data/state.json | python3 -c "import json,sys; d=json.load(sys.stdin); print('Balance:', d.get('balance', 'N/A'))"
```

## Key Checks
1. **No positions in AVOID list cities** — dallas, london, paris, hong-kong, tokyo, lucknow
2. **No positions in TIER 3 cities** — NYC, Toronto, Seoul, Shanghai, Seattle
3. **No single bet > $5.00** (max_bet paper)
4. **Balance not drawdown > 20%** from peak
5. **Morning METAR gate passed** for D+0 trades

## Position Limits
- `max_tier_to_trade: 2`
- `min_confidence: 0.75` for TIER 2
- `max_bet: $5.00` paper
- `kelly_fraction: 0.20`

## If Problem Found
1. Note affected positions
2. Flag for manual review
3. Do NOT modify without backtesting first
4. Document in observations

## Verification
```bash
pm2 status
pm2 logs alter-bot-v1 --nostream --lines 30
```
