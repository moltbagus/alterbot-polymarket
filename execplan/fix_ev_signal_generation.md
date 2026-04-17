# Fix EV Signal Generation - Select Highest EV Bucket

## Purpose / Big Picture

The weather trading bot is leaving money on the table by selecting the bucket with highest probability, not highest EV. When ECMWF forecasts 80.6°F for Miami, the bot picks the 80-81°F bucket (P=12.3%, EV=-71%) and skips trading because EV < 0.30. But the 86-87°F bucket has EV=+75% (market underpricing hot outcomes).

**After this fix:** The bot will scan ALL buckets and select the one with highest EV, not just the bucket containing the forecast.

## Progress

- [x] (2026-04-12 08:45 UTC+8) Identified root cause: bot selects bucket with highest P(bucket), not highest EV
- [ ] Implement fix to select highest EV bucket across all outcomes
- [ ] Validate fix with Miami April 13 test case
- [ ] Deploy and monitor

## Context and Orientation

**File to modify:** `/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py`

**Current buggy logic (lines ~1685-1710):**
```python
# Find the best bucket: highest Gaussian probability given the ensemble forecast.
# This selects the bucket where our forecast is most centrally positioned (best edge).
matched_bucket = None
best_bucket_prob = 0.0
for o in outcomes:
    if "range" not in o:
        continue
    t_low, t_high = o["range"]
    bp = bucket_prob(forecast_temp, t_low, t_high, sigma)
    if bp > best_bucket_prob:  # <-- BUG: selects by P, not EV
        best_bucket_prob = bp
        matched_bucket = o
```

**Key variables:**
- `forecast_temp` - ECMWF forecast temperature
- `sigma` - uncertainty (typically 2-4°C)
- `bucket_prob()` - calculates P(temp in bucket | forecast)
- `calc_ev()` - calculates EV given P and price

## Plan of Work

1. **Change selection criterion from P(bucket) to EV**
   - Instead of tracking `best_bucket_prob`, track `best_ev`
   - Calculate EV inside the same loop that calculates P
   - Select bucket with highest EV, not highest P

2. **Update the signal generation logic**
   - Keep the same output structure (best_signal dict)
   - Just change which bucket gets selected

## Concrete Steps

### Step 1: Modify the bucket selection loop

Find this code around line 1685:
```python
matched_bucket = None
best_bucket_prob = 0.0
for o in outcomes:
    if "range" not in o:
        continue
    t_low, t_high = o["range"]
    bp = bucket_prob(forecast_temp, t_low, t_high, sigma)
    if bp > best_bucket_prob:
        best_bucket_prob = bp
        matched_bucket = o
```

Replace with:
```python
matched_bucket = None
best_ev = -999.0
best_bucket_prob = 0.0
for o in outcomes:
    if "range" not in o:
        continue
    t_low, t_high = o["range"]
    ask = o.get("ask", o["price"])
    volume = o.get("volume", 0)
    
    # Skip if volume too low or price out of range
    if volume < MIN_VOLUME or ask <= 0.01 or ask >= 0.99:
        continue
    
    bp = bucket_prob(forecast_temp, t_low, t_high, sigma)
    ev = calc_ev(bp, ask)
    
    # Select bucket with HIGHEST EV (not highest P)
    if ev > best_ev:
        best_ev = ev
        best_bucket_prob = bp
        matched_bucket = o
```

### Step 2: Validate

After editing, test with Miami April 13:
- Before fix: No signal (best bucket 80-81°F has EV=-71%)
- After fix: Should find 86-87°F bucket with EV=+75%

Run: `python3.12 -c "..."` (test script)

## Validation

1. **Unit test:** Run the bucket selection with Miami data, verify highest EV bucket is selected
2. **Paper trade check:** Bot should start showing [DEBATE] for Miami after fix
3. **Deploy:** PM2 restart and monitor logs

## Decision Log

- 2026-04-12: Decision - Change from P(bucket) selection to EV selection. Rationale: EV is what matters for trading, not raw probability.
