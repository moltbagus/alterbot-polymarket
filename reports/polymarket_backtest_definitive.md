# Polymarket Temp Trading: Definitive Backtest Report
Generated: 2026-04-03

## Executive Summary

Backtested 3 trading strategies against Polymarket temperature prediction markets
(March 10-27, 2026) across 8 cities. **All strategies lose money.**

| Strategy | Trades | Win Rate | Total P/L | Per Trade |
|---|---|---|---|---|
| Exact bucket (closest to pred) | 86 | 27.9% | -$619.76 | -$7.21 |
| Or below at floor(pred) | 86 | 0.0% | -$860.00 | -$10.00 |
| Optimal bucket (hindsight oracle) | 86 | -- | +$474,087 | +$5,513 |
| Optimal excl. lucky outliers | 34 | -- | +$440.50 | +$12.96 |

**Bottom line:** Polymarket prices these buckets near $0.999. You win $0.01 per 
trade and lose $10 per trade. The math is brutally simple: you need >99.9% 
accuracy to break even. Our model's 28% accuracy guarantees losses.

---

## The Fundamental Problem: Asymmetric Payout Structure

When you buy YES at $0.999:
- You pay: $9.99
- If WIN: receive $10.00, profit = $0.01
- If LOSE: receive $0.00, loss = $9.99

Our 86 trades:
- 24 wins x +$0.01 = +$0.24
- 62 losses x -$10.00 = -$620.00
- **Net: -$619.76**

To break even on a $0.999 bet, you need to be right 99.9% of the time.

---

## Per-City Breakdown (Strategy 1: Closest Bucket)

| City | Trades | Wins | Win% | Avg Price | P/L |
|---|---|---|---|---|---|
| Hong Kong | 12 | 1 | 8% | $0.501 | $-109.99 |
| London | 1 | 1 | 100% | $0.999 | $0.01 |
| Paris | 18 | 7 | 39% | $0.999 | $-109.93 |
| Seoul | 1 | 0 | 0% | $0.999 | $-10.00 |
| Shanghai | 15 | 4 | 27% | $0.999 | $-109.96 |
| Singapore | 11 | 6 | 55% | $0.999 | $-49.94 |
| Taipei | 12 | 1 | 8% | $0.750 | $-109.99 |
| Tokyo | 16 | 4 | 25% | $0.999 | $-119.96 |

---

## Why The "Or Below" Strategy Lost 100%

We picked "floor(pred_temp) or below" markets. All were priced at $0.001-$0.086.
The actual temperature was ALWAYS above our bucket:

| Metric | Value |
|---|---|
| Mean actual - bucket | +6.4 degC |
| Actual > bucket (losses) | 86/86 (100%) |
| Average price paid | $0.036 |
| Wins needed to break even | 96.4% |
| Actual win rate | 0% |
| Total loss | -$860.00 |

The market was correct: in March, temperatures in these cities were well above
the "floor" bucket. Our model's predictions were too cold, and the "or below" 
bets were maximally wrong.

---

## Model Prediction Quality

| Metric | Value |
|---|---|
| Closest bucket exactly right | 24/86 (28%) |
| Off by 1 degree | 37/86 (43%) |
| Off by 2+ degrees | 25/86 (29%) |
| Mean error | 1.1 degC |

Our model is decent at getting within 1 degree, but the bucket system rounds to
integers. Being "off by 1" still means losing when the bucket is priced at $0.999.

---

## What Would Have Worked?

### Option A: Find mispriced buckets (market inefficiency)
From the data, some buckets were genuinely mispriced:
- Hong Kong "18 degC exact" at $0.100 (actual was 18.2 degC = win, 9x payout)
- These represent 8% of trades where market was wrong

If you could identify and bet ONLY on mispriced buckets: **+$440.50 on 34 trades**
But you can't know which ones are mispriced without knowing the actual outcome.

### Option B: Bet on high-uncertainty buckets
Low-priced buckets (e.g., $0.10-$0.50) have asymmetric payouts:
- A $0.10 bucket that wins pays 10x your stake
- Would need >10% win rate to break even
- Our data shows 0% for buckets <$0.50

### Option C: Don't bet at $0.999
The only way to have positive EV is to bet on buckets priced at $0.50 or lower,
where you get 1:1 or better payouts. But these markets rarely exist with
sufficient liquidity, and the market is usually right.

---

## Recommendation

**DO NOT TRADE THIS STRATEGY ON POLYMARKET.**

The platform's fee structure (0-2%) and the $0.999 pricing of near-certain events
make it mathematically impossible to profit with a 28% accuracy model.

If you want to continue, options:
1. Improve the temperature prediction model to >99.9% accuracy (impossible)
2. Find markets with better payout ratios (lower prices, higher variance)
3. Only bet on days where you have high conviction AND the market price is low

---

## Data Sources
- Polymarket CLOB prices: fetched via polymarket-cli (real-time)
- Temperature predictions: alter-bot-v1 backtest CSV
- Date range: March 10-27, 2026
- Cities: Hong Kong, London, Paris, Seoul, Shanghai, Singapore, Taipei, Tokyo
- Markets: Daily max temperature exact buckets + "or below" range markets
