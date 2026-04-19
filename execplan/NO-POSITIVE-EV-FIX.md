# ExecPlan: Alter-Bot Positive EV Fix
**Status:** IN PROGRESS  
**Updated:** 2026-04-19 12:45 MYT

## Root Cause (Confirmed)

The bot is correctly disciplined — there ARE no positive EV trades in these markets. But the bot has fundamental optimization gaps that prevent it from finding edges that DO exist.

### The 5 Real Problems

**Problem 1: Single-bucket thinking**
The bot evaluates each 1°F bucket independently. It never compares ADJACENT buckets for mispricing. Miami [82,83] at $0.59 and [84,85] at $0.56 is a market INVERSION — the higher bucket is cheaper, but the forecast (84.4°F) strongly supports [84,85]. This is a positive EV pair trade.

**Problem 2: Sigma is too high**
Atlanta's sigma_override is 1.46°C (3.5°F), but when models agree perfectly (ECMWF=74, HRRR=74), sigma should be 0.73°C (0.9°F). The high sigma deflates bucket probabilities to ~18% even when the forecast is centered in the bucket.

**Problem 3: No model bias correction in probability**
ECMWF runs COLD in April. The raw forecast of 74°F might need +2°F bias to 76°F before computing bucket probability. The current code applies bias AFTER probability calculation, so the probability is wrong from the start.

**Problem 4: No cumulative probability analysis**
The correct signal for "will highest temp be ≤ 85°F?" is P(T ≤ 85°F) not P(T in [84,85]). Cumulative probability gives a more robust edge signal, especially for edge buckets.

**Problem 5: Config conflicts**
`tier_1_strong: ["miami","paris","london"]` still in config but MEMORY says Atlanta is best. Config needs cleanup.

## Key Data

```
Atlanta Apr 20: forecast 75.8°F | models agree (74,74) | best bucket [74,75] at $0.675
Miami Apr 20: forecast 84.4°F | models slightly disagree (82,83) | [84,85] at $0.56
Sao Paulo Apr 20: forecast 25.xx | 26°C bucket at $0.635 might be mispriced
```

## Fixes Required

### Fix 1: Adjacent Bucket Comparison (CRITICAL)
Add logic to detect when adjacent buckets have inverted pricing:
```python
# After computing bucket probabilities
# Check for pricing inversions across adjacent buckets
for i in range(len(buckets) - 1):
    b1, b2 = buckets[i], buckets[i+1]
    if b1['price'] < b2['price'] and forecast > midpoint(b1):
        # Market is inverted: higher bucket cheaper than lower bucket
        # This is a PAIR TRADE opportunity
        edge = (p_b2 - b2['price']) + (p_b1 - b1['price'])
```

### Fix 2: Dynamic Sigma from Model Disagreement
```python
def get_dynamic_sigma_v2(city, ecmwf_raw, hrrr_raw, base_sigma):
    disagreement = abs(ecmwf_raw - hrrr_raw)
    factor = 1.0 + (disagreement / 3.0)  # 0°F → 1.0x, 3°F → 2.0x
    return round(base_sigma * factor, 2)
```

### Fix 3: Pre-bias Probability Correction
```python
# Apply model bias BEFORE computing probability, not after
adjusted_forecast = forecast_temp + BIAS_CORRECTION[city]
# Then compute bucket probability using adjusted_forecast
```

### Fix 4: Cumulative Probability Mode
For markets where the question is "≤ X°F", use P(T ≤ X) cumulative:
```python
def cumulative_bucket_prob(forecast, t_high, sigma):
    """P(T <= t_high) using norm_cdf"""
    return norm_cdf((t_high - forecast) / sigma)
```

### Fix 5: Config Cleanup
Remove conflicting tier entries.

## Validation

After fixes, the bot should identify:
- Atlanta [76,77] at $0.645 with tight sigma (0.9°F) → edge = +0.07
- Miami [84,85] vs [82,83] pair trade → edge through inversion
- Any bucket where P_forecast > P_market by > 5%

## Progress

- [x] Root cause analysis complete
- [ ] Implement Fix 1: Adjacent bucket comparison
- [ ] Implement Fix 2: Dynamic sigma from model disagreement  
- [ ] Implement Fix 3: Pre-bias probability correction
- [ ] Implement Fix 4: Cumulative probability mode
- [ ] Implement Fix 5: Config cleanup
- [ ] Test and validate
