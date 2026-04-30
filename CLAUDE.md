# alter-bot-v1 — Claude Code Project Guidelines

## Project Context

Polymarket weather prediction bot. Paper trading on Sepolia testnet.
Bot: `bot_v2.py`. Config: `config.json`. State: `data/state.json`.

## Hard Rules (Would cause mistakes if removed)

**These are not suggestions. Removing any line causes immediate bugs.**

- **NEVER commit `.env` files or secrets** — API keys, private keys, tokens must stay local only
- **All `async` calls must use `try/except`** — bare async calls crash the event loop on rejection
- **Prefix commits: `feat:`, `fix:`, `docs:`, `refactor:`** — without prefix, commit is uninformative
- **Run `py_compile` after every code change** — syntax errors block the bot restart; catch before PM2 does
- **Bot state lives in `data/state.json`** — never rely on in-memory state across restarts
- **Circuit breakers must persist to `state.json`** — in-memory circuit breakers reset on PM2 restart (known bug)

## Project Conventions

- PM2 process name: `alter-bot-v2` (legacy name, points to same code)
- Restart command: `pm2 restart alter-bot-v2`
- Log command: `pm2 logs alter-bot-v2 --lines 50 --nostream`
- Balance: paper only, no real funds
- Trading: Polymarket Sepolia testnet

## Python Standards

- Use `pathlib.Path` for file paths (not `os.path`)
- All file reads/writes: `try/except FileNotFoundError` + JSON parse errors
- No bare `except:` — always catch specific exceptions
- `python3 -m py_compile bot_v2.py` before every restart

## When Fixing Bugs

1. Read the ExecPlan first (`execplan/*.md`)
2. Reproduce before fixing
3. Fix and verify with test cases
4. Run `py_compile` — pass = safe to restart
5. Check `slippage_log` and `fill_log` for correct output
6. After restart, confirm balance in logs matches `state.json`
