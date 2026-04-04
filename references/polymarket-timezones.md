# Polymarket Weather Trading - Timezone Reference
# Saved: April 4, 2026

## City Timezones (DST-aware)

| City | Timezone | April Offset |
|---|---|---|
| Paris | CET/CEST | UTC+2 (CEST) |
| London | GMT/BST | UTC+1 (BST) |
| Tokyo | JST | UTC+9 |
| Hong Kong | HKT | UTC+8 |
| Taipei | CST | UTC+8 |
| Miami | EST/EDT | UTC-4 (EDT) |
| Atlanta | EST/EDT | UTC-4 (EDT) |
| Singapore | SGT | UTC+8 |
| Sao Paulo | BRT | UTC-3 |

## DST Rules

- Northern Hemisphere: DST starts last Sunday March, ends last Sunday October
- Paris 2026: Clocks forward March 29, back October 25

## ALL Polymarket endDate in UTC - convert to local city time

## April 2026 Examples
| UTC | Paris | London | Tokyo |
|---|---|---|---|
| 12:00Z | 14:00 | 13:00 | 21:00 |
| 09:00Z | 11:00 | 10:00 | 18:00 |

## Error to never repeat
Paris April 4 16C market: endDate 12:00Z = 14:00 Paris (CEST UTC+2).
Never say a market is closed when there are hours left before the endDate UTC.
