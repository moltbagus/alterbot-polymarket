# alter-bot-v1: Bias Recalibration + EV Calibration Fixes

This ExecPlan is a living document. Follow PUA methodology — reproduce→localize→fix→guard. Owner: TIGER001, delegated to Turing.

## Purpose / Big Picture

Three distinct problems:
1. **Shanghai bias** — currently +8.0, overcorrected. Historical avg_error 6.57°C but recent April 28 sample shows only +2.3°C error. Should be ~+4.5.
2. **Southern Hemisphere season sign** — Wellington (+1.5) and Buenos Aires (-1.5) bias values may have wrong signs for April autumn season
3. **EV calibration** — negative EV positions winning, positive EV losing. Bucket probability miscalibrated vs actual outcomes.

After fixes: bot makes more calibrated bets with correct bias values and properly calibrated probability estimates.

## Progress

- [ ] (2026-04-29 05:46 MYT) Fix Shanghai bias: +8.0 → +4.5
- [ ] (2026-04-29 05:46 MYT) Investigate Southern Hemisphere bias sign logic
- [ ] (2026-04-29 05:46 MYT) Find root cause of EV miscalibration (negative EV winning = probability estimate too pessimistic)
- [ ] (2026-04-29 05:46 MYT) Fix and verify, py_compile, restart

## Context and Orientation

**Key files:**
- `alter-bot-v1/bot_v2.py` — BIAS_CORRECTION dict at line 152, bucket_prob_cumulative at line 825
- `alter-bot-v1/data/city_error_history.json` — historical error data per city

**City error history (critical evidence):**

| City | bias (fcast-actual) | avg_error | win_rate | n | Notes |
|------|---------------------|-----------|----------|---|-------|
| shanghai | -6.57 | 6.57°C | 0% | 3 | CIRCUIT BROKEN |
| wellington | -1.62 | 1.62°C | 33% | 3 | Very few samples |
| buenos-aires | +3.43 | 3.43°C | 0% | 2 | Very few samples |
| atlanta | -1.90 | 5.11°C | 73% | 30 | BEST PERFORMER |
| sao-paulo | +1.41 | 3.47°C | 55% | 33 | Decent |
| london | -3.04 | 3.48°C | 0% | 25 | Circuit broken |

**Bias sign convention:**
- Positive bias in BIAS_CORRECTION = ADDED to forecast → raises adjusted forecast
- In city_error_history: bias = forecast - actual → negative means forecast too LOW (actual warmer)
- For shanghai: bias=-6.57 means model is COLD by 6.57°C → need positive bias correction ✓
- For wellington: bias=-1.62 means model is COLD → need positive bias? But current = +1.5 ✓
- For buenos-aires: bias=+3.43 means model is HOT → need negative bias? But current = -1.5 (correct direction)

## Shanghai Bias Fix

**Current:** +8.0°C
**Problem:** Based on 3 samples: errors of 8.3, 9.1, 2.3°C. The first two are extreme outliers (April 27 anomalous weather). Most recent sample (Apr 28) shows only +2.3°C error.
**Fix:** Set to +4.5°C — midpoint between the 3 samples' avg (6.57) and the most recent signal (2.3). Not purely reactive to one sample.

```python
"shanghai": +4.5,  # Updated from +8.0 (was overcorrected from 3 samples with 2 extreme outliers)
```

## Southern Hemisphere Bias Investigation

**Current state:**
- wellington: +1.5 (positive bias = forecast raised)
- buenos-aires: -1.5 (negative bias = forecast lowered)

**Evidence from city_error_history:**
- wellington: avg_error 1.62°C, forecast was LOW (bias=-1.62 in fcast-actual). So positive +1.5 bias is moving in correct direction to RAISE the forecast.
- buenos-aires: avg_error 3.43°C, forecast was HIGH (bias=+3.43 in fcast-actual). So negative -1.5 bias is moving in correct direction to LOWER the forecast.

**Investigation needed:**
1. Check if bias is being applied correctly — look at `apply_bias()` function
2. The "wrong season sign" issue: in April, Southern Hemisphere is entering autumn. If the ECMWF model doesn't capture seasonal cooling, the bias pattern for autumn months may be wrong.
3. Look at `bucket_prob_cumulative` — when forecast is raised by +1.5 for wellington, P(T <= threshold) increases → if betting YES (T>=threshold), this makes YES less likely.
4. Check if the MARKET side (YES/NO) is consistent with bias direction.

**Find and read apply_bias:**
```bash
grep -n "def apply_bias" alter-bot-v1/bot_v2.py
# Read the full function
```

## EV Calibration — Root Cause Analysis

**Symptom:** Negative EV positions winning, positive EV losing.
**This means:** The probability estimate `p` used in `calc_ev` is systematically wrong.

**How p is derived (trace the code):**
1. `bucket_prob_cumulative(forecast, target_temp, sigma, bias)` → returns probability P(T <= target_temp)
2. This `p` is used in `calc_ev(p, price, side)`

**Possible root causes:**

A) **Wrong sigma** — sigma=1.5 may be too wide, making probabilities too extreme (near 0 or 1)
B) **Bias not applied at right step** — bias might be applied AFTER probability calculation instead of BEFORE
C) **Bucket type confusion** — P(T <= X) vs P(T >= X) confusion flipping the probability

**Find where bucket_prob_cumulative is called:**
```bash
grep -n "bucket_prob_cumulative" alter-bot-v1/bot_v2.py | head -20
```

Read each call site. Verify:
1. Is bias being passed to bucket_prob_cumulative?
2. Is the sigma correct for the city?
3. Is the probability being interpreted correctly for YES vs NO bets?

## Concrete Steps

```bash
# 1. Read apply_bias function
sed -n '999,1050p' alter-bot-v1/bot_v2.py

# 2. Find all bucket_prob_cumulative calls
grep -n "bucket_prob_cumulative" alter-bot-v1/bot_v2.py

# 3. Read the main probability calculation flow (look for where p is derived for calc_ev)
grep -n "calc_ev\|bucket_prob" alter-bot-v1/bot_v2.py | head -30

# 4. Check for any city-specific sigma overrides
grep -n "sigma" alter-bot-v1/bot_v2.py | head -30
```

## Validation and Acceptance

1. **Shanghai:** After fix to +4.5, next resolution should show error closer to 0 (not 8-9°C)
2. **Southern Hemisphere:** Bias values reviewed — if sign is wrong, flip. If correct direction, document why "wrong season sign" was suspected.
3. **EV calibration:** Find the root cause — p should accurately reflect actual win probability. When p=0.7 and price=0.65, actual win rate should be ~70%, not ~30%.

## Decision Log

- Decision: Set Shanghai bias to +4.5 (midpoint between 6.57 avg and 2.3 recent)
  Rationale: +8.0 was overcorrecting based on 2 extreme outlier samples. +4.5 is conservative.
  Date/Author: 2026-04-29 / TIGER001

- Decision: Investigate Southern Hemisphere bias before changing
  Rationale: city_error_history suggests current directions are correct. "Wrong season sign" claim may be wrong — need evidence before flipping signs.
  Date/Author: 2026-04-29 / TIGER001

## Surprises & Discoveries

TBD

## Outcomes & Retrospective

TBD
