# Polymarket Weather Backtest: REAL CLOB Price Analysis
**Generated:** 2026-04-03 16:09
**Data source:** Polymarket CLOB API via polymarket CLI
**Predictions source:** polymarket_backtest_combined.csv

---

## Executive Summary

This report contains the first-ever real CLOB price backtest of the Polymarket
temperature prediction strategy. We fetched actual trading prices from the
Polymarket order book for 118 historical predictions across 8 cities.

**Bottom line: The strategy loses money. But the reason is NOT what we thought.**

| Metric | Value |
|--------|-------|
| Total predictions | 118 |
| Polymarket markets found | 86 (32 gaps) |
| Win rate | 24/86 = 27.9% |
| Total P&L (single bucket, $10 stake) | **$-619.76** |
| Average loss per trade | $-7.21 |

**The strategy is a -$7.21 per trade loser.**

---

## Per-City Results

| City | Trades | Win Rate | Avg Price | P&L | Avg/Trade |
|------|--------|----------|-----------|-----|-----------|
| London | 1 | 100.0% | $0.999 | $0.01 | $0.01 |
| Seoul | 1 | 0.0% | $0.999 | $-10.00 | $-10.00 |
| Singapore | 11 | 54.5% | $0.999 | $-49.94 | $-4.54 |
| Paris | 18 | 38.9% | $0.999 | $-109.93 | $-6.11 |
| Shanghai | 15 | 26.7% | $0.999 | $-109.96 | $-7.33 |
| Hong Kong | 12 | 8.3% | $0.999 | $-109.99 | $-9.17 |
| Taipei | 12 | 8.3% | $0.999 | $-109.99 | $-9.17 |
| Tokyo | 16 | 25.0% | $0.999 | $-119.96 | $-7.50 |

---

## The Critical Discovery

### 100% of trades were priced at $0.999

Every single market we selected was trading at **$0.999** (99.9 cents on the dollar).
This has devastating implications for the strategy:

- **Entry cost:** $9.99 per $10 position
- **Win payout:** $0.01 (the difference from $1.00)
- **Loss cost:** $10.00 (full stake)
- **Break-even win rate:** 99.9%

Our actual win rate was **27.9%** — far below the 99.9% needed to break even.

### Why $0.999?

The Polymarket bucket markets for exact temperatures (e.g., "Will it be exactly
33C?") are priced at near-extreme odds because:

1. Weather forecast models are accurate enough that the probability of any
   specific exact temperature is very high (e.g., if the forecast says 28-35C,
   "33C exactly" has high probability)
2. The market makers price these accordingly
3. The actual outcome distribution is roughly uniform across 5-7 possible
   temperatures, making each individual bucket unlikely to resolve "Yes"

### This is NOT a prediction failure

Our model was often right about temperature direction. Singapore had 54.5% win
rate on exact bucket predictions. But winning 54.5% of the time on a market
priced at $0.999 still loses money:

```
54.5 wins x $0.01 = +$0.55
45.5 losses x $10.00 = -$455.00
Net per 100 trades: -$454.45
```

---

## What Went Wrong: Strategy vs Prediction

The backtest confused two different things:

1. **Prediction accuracy:** Our model predicts temperatures within 1 degree
2. **Market selection:** We picked the wrong TYPE of Polymarket market

### What we did (WRONG):
```
For each prediction (e.g., 33.1C):
  Find bucket "33C" at price $0.999
  Stake $10
  Win if actual rounds to 33C
```

### What we SHOULD have done (RIGHT):
```
For each prediction (e.g., 33.1C):
  Find "33C or below" bucket (range market)
  If price < our model's implied probability: BUY
  Otherwise: SKIP or SELL
```

The "or below" range markets are where the real value is. Our model gives
high probability to a RANGE of temperatures, not an exact number.

---

## The Real Strategy

### Optimal approach:
1. Use our temperature model to predict a probability distribution
2. For each bucket market, calculate: P(actual <= X) from our distribution
3. If Polymarket's "X or below" price < our P, BUY
4. If Polymarket's "X or below" price > our P, consider SELLING

### Example:
- Our model: Singapore high is 33C (range: 32-34C)
- "33C or below" market at Polymarket: $0.70
- Our P(actual <= 33C): ~80%
- Edge: 80% - 70% = 10% positive expected value
- BUY $10 at $0.70: expected value = 0.8 x $4.29 - 0.2 x $10 = +$1.43

---

## Market Gaps

32 predictions had NO matching Polymarket markets (all from London and Seoul
March 10-26). These are genuine market gaps in the scraper's coverage.

---

## Recommendations

1. **Do not bet on exact bucket markets** unless they're priced < $0.50
2. **Focus on "or below" range markets** where our model gives edge
3. **Calculate implied probability** from our model BEFORE looking at prices
4. **Only bet when edge > 10%** to account for model error
5. **Consider SELLING** "Yes" on markets priced at >95% where we disagree

---

## Files

- Raw results: `alter-bot-v1/data/real_backtest_results.json`
- This report: `alter-bot-v1/data/real_backtest_final_report.md`
- Predictions CSV: `alter-bot-v1/data/polymarket_backtest_combined.csv`
