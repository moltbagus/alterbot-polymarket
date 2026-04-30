# Weekly Backtest & Performance Review

*Schedule: Every Sunday at 20:00 MYT (12:00 UTC)*

## Purpose
Weekly deep-dive on win rates, EV capture, city tier performance, and self-improvement progress.

## What to Review
1. **Win rate by city tier** — TIER 1 should be 90%+
2. **EV capture** — Are we actually trading positive-EV opportunities?
3. **Sigma accuracy** — Are forecast errors tracking within sigma bands?
4. **Self-improvement** — New observations processed, sigma updated?
5. **Config drift** — Any parameters that drifted without backtesting?
6. **TA debate quality** — Are TradingAgents debates producing useful signals?

## Commands
```bash
cd ~/.openclaw/workspace/alter-bot-v1

# Win rate analysis
python3 proper_backtest.py 2>&1 | grep -E "(win_rate|TRUE|FALSE|tier|Sharpe)"

# City optimizer
python3 city_optimizer.py 2>&1 | tail -30

# Self-improvement summary
python3 self_improver.py process 2>&1 | tail -40

# Full report
python3 bot_v2.py report 2>&1 | head -100

# Fill analysis
python3 -c "from fill_tracker import print_fill_report; print_fill_report()"
```

## Output
- Update `reports/weekly-review-YYYY-MM-DD.md`
- Note any config changes needed
- Alert via Telegram if win rate < 80% or any TIER 1 city underperforming

## Thresholds
- Alert if TIER 1 win rate < 85%
- Alert if avg EV < 0.05 on filled trades
- Alert if sigma seems systematically wrong (errors outside 2σ)
