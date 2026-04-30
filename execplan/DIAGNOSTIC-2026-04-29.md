# Alter-Bot-v1 Crash Diagnostic & Fix — 2026-04-29

## Purpose / Big Picture

The bot is crashing and burning — it enters a crash loop every 10-60 minutes with a `NameError: name 'save_config' is not defined` that kills the entire run loop. The fix is straightforward: move the call to `save_config(_cfg)` to the ONLY place where it's actually called (inside `_persist_circuit_broken_city` at line 1604), which is already a function that exists and is defined at line 1582. The function `save_config` IS defined at line 1582 — so the NameError is strange. We need to verify the pycache is in sync with the source file, and fix any stale bytecode.

## Progress

- [ ] (2026-04-29 22:46 MYT) Diagnose the NameError source — is it a pycache mismatch or code bug?
- [ ] Fix the crash: ensure save_config is reachable from _persist_circuit_broken_city
- [ ] Clear stale pycache and restart bot
- [ ] Verify the bot runs for at least 2 full cycles without crashing

## Context and Orientation

Key files and what they do:
- `bot_v2.py` — main trading bot, 2952 lines, runs under PM2 as `alter-bot-v2`
- `config.json` — live config with blocked_cities and other parameters
- `data/state.json` — balance, positions, circuit broken cities
- `__pycache__/bot_v2.cpython-314.pyc` — compiled bytecode (last modified 19:48, source last modified 17:46)

Critical functions:
- `save_config(cfg)` — defined at line 1582, writes config.json to disk
- `_persist_circuit_broken_city(city_slug, error_count)` — defined at line 1586, persists circuit broken cities; calls `save_config(config)` at line 1604
- `scan_and_update()` — defined at line 2343, main scan cycle; calls `_persist_circuit_broken_city` at lines 2390 and 2516 (via try/except)

## The Symptom

PM2 logs show repeated crash cycles:
```
Traceback (most recent call last):
  File ".../bot_v2.py", line 2175, in scan_and_update
    _circuit_broken.add(city_name)
NameError: name 'save_config' is not defined

During handling of the above exception, another exception occurred:
  File ".../bot_v2.py", line 2644, in run_loop
    new_pos, closed, resolved, balance = scan_and_update()
  File ".../bot_v2.py", line 2175, in scan_and_update
    _circuit_broken.add(city_name)
NameError: name 'save_config' is not defined
```

The bot was started at 09:50 UTC (17:50 MYT) and has been running ~5 hours (4 restarts). The crash happens inside the main `while True` loop in `run_loop`, caught by the generic `Exception` handler which prints the error and sleeps 60 seconds before retrying.

## Surprises & Discoveries

- **Confusing line number**: The traceback says line 2175 inside `scan_and_update`, but line 2175 of the actual file is a comment (`# This was the main cause of oversized bets and 39.6% drawdown.`). The bytecode file is from Python 3.14, but the PM2 process uses `/usr/bin/python3.12`. Python 3.12 and 3.14 have different bytecode structures, so a .pyc compiled for one won't work for the other.
- **Source and bytecode out of sync**: The bot_v2.py source was last modified at 17:46 MYT but the pycache was recompiled at 19:48 MYT — someone ran the bot AFTER the last source edit and the cache was regenerated.
- **File sizes don't match**: Source is 135846 bytes, bytecode is 135974 bytes — different sizes, confirming bytecode != compiled(source).
- **save_config IS defined at line 1582**: `def save_config(cfg):` exists in the source. The NameError is not a missing function definition — it's a scope or import issue.

## Plan of Work

1. **Verify the exact bytecode being run**: The pyc was compiled with Python 3.14 but PM2 runs python3.12. Check if there are multiple bot_v2.py files and trace exactly which one PM2 executes.

2. **Check for circular import or scope shadowing**: `save_config` is defined at line 1582 inside the module, so it should always be accessible to `_persist_circuit_broken_city`. But if there's an import-time error or early bailout, the function might not be registered. Look for `import save_config` or `from ... import save_config` anywhere in the file.

3. **Write the fix**: Add `global save_config` inside `_persist_circuit_broken_city` if the function is being shadowed, OR simply verify `save_config` is reachable and just do a clean pycache clear + restart.

4. **Root cause — verify by inspection**: Compare `_persist_circuit_broken_city`'s bytecode line number (2175) against the actual source. If they're different, the pycache is stale and needs clearing.

## Concrete Steps

### Step 1: Check Python version mismatch

```bash
# Check Python version used by PM2
pm2 describe alter-bot-v2 | grep interpreter

# Check Python version available
python3 --version
python3.12 --version
python3.14 --version 2>/dev/null || echo "no python3.14"

# Check if there's a separate python3.14 binary
which python3.14 2>/dev/null || echo "no python3.14 in PATH"
```

### Step 2: Search for any shadowing of save_config

```bash
# Look for any import of save_config from another module
grep -n "from.*import.*save_config\|import.*save_config" bot_v2.py

# Check the bytecode line 2175 in the source file
# If the error says line 2175 but actual code at 2175 is a comment,
# it means the bytecode is from a different version of the source
sed -n '2175p' bot_v2.py

# Count lines in scan_and_update
python3 -c "
import sys
sys.path.insert(0, '.')
import bot_v2, inspect
src = inspect.getsource(bot_v2.scan_and_update)
print(f'scan_and_update: {len(src.splitlines())} lines')
"

# Check how many lines are in the compiled scan_and_update bytecode
python3.12 -c "
import py_compile, dis, tempfile, os
src = 'bot_v2.py'
# compile using python3.12
with open(src) as f:
    code = compile(f.read(), src, 'exec')
# Find scan_and_update
for const in code.co_consts:
    if hasattr(const, 'co_name') and const.co_name == 'scan_and_update':
        print(f'scan_and_update bytecode lines: {const.co_firstlineno} to {const.co_firstlineno + len(const.co_code) // 8}')
        break
" 2>&1 || echo "Use dis module differently"
```

### Step 3: Clear stale pycache and recompile

```bash
# Remove all pycache files for bot_v2
rm -f __pycache__/bot_v2.cpython-*.pyc

# Recompile with python3.12 (the version PM2 uses)
python3.12 -m py_compile bot_v2.py && echo "Compile OK"

# Verify bytecode size
ls -la __pycache__/bot_v2.cpython-312.pyc
```

### Step 4: Restart the bot

```bash
pm2 restart alter-bot-v2 && echo "Restarted OK"
pm2 logs alter-bot-v2 --nostream --lines 20
```

### Step 5: Verify stable for 2 cycles

```bash
# Watch for 3 minutes (at least 2 full monitor cycles + 1 scan interval)
# Expected: no Traceback, no NameError, regular "[HH:MM:SS] monitoring positions..." output
sleep 180 && pm2 logs alter-bot-v2 --nostream --lines 30 | grep -v "^$"
```

## Validation and Acceptance

The bot is fixed if:
1. No `NameError` in PM2 logs after restart
2. `[HH:MM:SS] full scan...` or `[HH:MM:SS] monitoring positions...` appears every minute for at least 3 consecutive cycles
3. Balance stays at $666.90 (no unexpected changes from crashes)

## Idempotence and Recovery

- If the fix doesn't work, the pycache is not the issue — inspect `save_config` scope more deeply
- If the bot still crashes with NameError after pycache clear, add `from bot_v2 import save_config` inside `_persist_circuit_broken_city` OR use a top-level wrapper
- If bot crashes with a different error (e.g., `KeyError: 'source'`), that's a separate pre-existing bug — treat as new incident

## Decision Log

- 2026-04-29 22:46 MYT: Identified that bot is in crash loop with `NameError: name 'save_config' is not defined`. Source has `save_config` defined at line 1582, so issue is bytecode/source mismatch. pyc is python 3.14 but PM2 runs python 3.12.

## Artifacts

PM2 error transcript:
```
0|alter-bo | NameError: name 'save_config' is not defined
0|alter-bo |   File "/home/alyssa/.openclaw/workspace/alter-bot-v1/bot_v2.py", line 2175, in scan_and_update
0|alter-bo |     _circuit_broken.add(city_name)
0|alter-bo |         ^^^^^^^^^^^
```

Bot status at diagnosis:
```
alter-bot-v2 | online | 4 restarts | 5h uptime | balance $666.90
Last scan: 2026-04-29 22:39:31 MYT (7 min ago)
Circuit broken: tokyo, singapore, nyc, hong-kong, toronto, paris, buenos-aires, london, shanghai
```