# Fix Manifest: EV Formula Calculation Error

## Alert Summary
- **Trigger:** EV (Expected Value) calculation uses wrong formula — `p - price` instead of proper Kelly-derived formula
- **Source:** `data/p0_alerts.json` → `ev_formula_error`
- **Severity:** P1

## Root Cause

The EV calculation in `calc_ev()` uses a simplified `p - price` which:
1. Ignores the payout ratio (what you win vs what you stake)
2. Doesn't account for Kelly fraction (f/2, f/4, etc.)
3. Can rank a 5% edge at 50:1 odds the same as 5% edge at 1:1 odds

**Correct Kelly formula:**
```
EV = (p * B) - (1 - p)  [binary/yes-no market]
where B = payout_ratio (e.g., 0.95 for ~1.95x return on yes)

Or more generally for fractional Kelly:
EV = (p * (b + 1) - 1) * fraction
where b = decimal odds - 1
```

**Current problematic formula:**
```python
ev = p - price  # WRONG — ignores payout structure
```

**Related code path:**
- `bot_v2.py:calc_ev()` — EV calculation function
- `bot_v2.py:score_city()` — where EV is used to rank cities

## Fix Required

### 1. Fix calc_ev() to use proper Kelly-based formula
**File:** `bot_v2.py`
**Function:** `calc_ev()`

```python
# BEFORE (wrong):
def calc_ev(p, price):
    """p = probability, price = current price"""
    return p - price  # WRONG: ignores payout structure

# AFTER (correct):
def calc_ev(p, price, kelly_fraction=0.25):
    """
    p = probability (0-1)
    price = current price (for yes/no market, what you pay per share)
    kelly_fraction = fraction of Kelly to use (default 0.25 = quarter Kelly)
    
    For a yes/no binary market at price P:
    - Payout on yes = 1/P (you get 1 if yes, 0 if no)
    - EV = p * (1/P) - (1-p) * 1
    - With Kelly fraction f: EV = f * (p * (1/P) - (1-p) * 1)
    """
    if price <= 0 or price >= 1:
        return 0.0
    
    # Payout ratio: what you get back per unit staked if yes
    payout_per_unit = (1.0 / price) - 1  # e.g., price=0.5 → payout=1.0 (double)
    
    # Expected value per unit staked
    ev_per_unit = (p * payout_per_unit) - (1 - p)
    
    # Apply Kelly fraction
    return kelly_fraction * ev_per_unit


# ALTERNATIVE simpler version:
def calc_ev_simple(p, price):
    """
    Simplified EV for binary markets.
    EV = expected return per dollar bet.
    """
    if price <= 0 or price >= 1:
        return 0.0
    # Win: you get (1/price) dollars for 1 dollar bet
    # Lose: you lose 1 dollar
    expected_winnings = p * (1.0 / price)
    expected_losses = (1 - p) * 1.0
    return expected_winnings - expected_losses
```

### 2. Update score_city() to use EV correctly
**File:** `bot_v2.py`
**Function:** `score_city()`

Ensure EV is the primary ranking factor, not conviction or other heuristics:

```python
def score_city(city, forecast, actual, ...):
    ev = calc_ev(p=forecast, price=current_price)
    
    # Rank by EV, not conviction
    # Conviction can still gate (min_ev_threshold)
    if ev < MIN_EV_THRESHOLD:
        return None
    
    return {
        "city": city,
        "ev": ev,
        "forecast": forecast,
        ...
    }
```

## Verify Steps

1. Review `calc_ev()` in bot_v2.py — confirm current formula
2. Test with known edge cases:
   - `p=0.6, price=0.5` → should have positive EV (expected win)
   - `p=0.3, price=0.5` → should have negative EV
   - `p=0.95, price=0.9` → small positive EV
   - `p=0.1, price=0.9` → large negative EV
3. Compare rankings before/after fix — ensure high-conviction high-odds cities rank correctly
4. Run paper trading for 1 week — confirm EV-positive cities outperform

## Test Case

```
Scenario 1: Strong favorite
p = 0.8 (80% chance)
price = 0.82 (paying 0.82 for 1.0 if yes)
payout = 1/0.82 - 1 = 0.22
EV = 0.8 * 0.22 - 0.2 = 0.176 - 0.2 = -0.024 (slightly negative)

Scenario 2: Underdog with value
p = 0.3 (30% chance)
price = 0.25 (paying 0.25 for 1.0 if yes)
payout = 1/0.25 - 1 = 3.0
EV = 0.3 * 3.0 - 0.7 = 0.9 - 0.7 = +0.20 (POSITIVE — value bet!)

Expected: Underdog value bet ranks HIGHER than overpriced favorite
```
