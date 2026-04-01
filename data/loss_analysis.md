# Loss Analysis - What We Learned

## Worst Performing Cities (0% win rate)
- Tel Aviv: 0/3 - Hot desert climate, extreme temps
- Seoul: 0/2 - Complex monsoon patterns
- Singapore: 0/1 - Tropical, rain unpredictability
- Chicago: 0/2 - Lake effect, extreme variability
- NYC: 0/2 - Coastal weather changes
- Paris: 0/2 - Atlantic weather variability
- Wellington: 0/2 - Wind patterns unpredictable

## Root Causes
1. **Extreme variability** - Cities with high weather variance (Chicago, NYC)
2. **Rain impact** - Tropical cities with afternoon thunderstorms (Singapore, Seoul)
3. **Sea breeze** - Coastal cities with complex wind patterns (Wellington)
4. **Desert heat** - Tel Aviv extreme heat events

## Improvements Needed
1. **Add rain penalty** - Reduce confidence when rain expected
2. **Increase sigma** - More uncertainty for volatile cities
3. **Better source data** - Use local METAR over global models
4. **Pattern detection** - Identify weather patterns before trading

## New Rules Implemented
- If precip >30%: reduce confidence by 20%
- Increase sigma_mult by 0.3 for cities with >50% variance
- Require METAR confirmation before trading in volatile cities
- Add sea breeze detection for coastal cities
