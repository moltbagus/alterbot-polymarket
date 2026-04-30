# Alter-Bot P0 Fix Index

Generated: 2026-04-30 14:04 UTC
Total alerts routed to Turing: 0

## Plugin Registry

| ID | Name | Severity | Enabled |
|----|------|----------|---------|
| `PORTFOLIO_DRAWDOWN` | Portfolio Drawdown >30% | P0 | ✅ |
| `US_UNIT_MISMATCH` | US City Unit Mismatch | P0 | ✅ |
| `CITY_POOR_PERFORMANCE` | City Circuit Breaker / Poor Performance | P0 | ✅ |
| `EV_FORMULA_WRONG` | EV Formula Calculation Error | P1 | ✅ |
| `WHALE_SKIP_NOT_CAPTURED` | Whale Skip Reason Not Tracked | P1 | ✅ |

## Active Alerts

## Architecture

Each P0 type is a **plugin** in `P0_PLUGINS`. To add a new P0 type:
1. Write a fix manifest in `fixes/<name>.md`
2. Add a `check_fn` that returns alert dicts
3. Add one dict entry to `P0_PLUGINS` — no other code changes needed
