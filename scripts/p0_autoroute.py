#!/usr/bin/env python3
"""
Alter-Bot P0 Auto-Route
========================
Reads p0_alerts.json, spawns Turing to fix each issue.
Designed to run AFTER p0_alert_detector.py finds P0 conditions.
Run from cron: every 15 minutes after p0_alert_detector.py.

Usage:
  python3 p0_autoroute.py          # dry run (shows what would be routed)
  python3 p0_autoroute.py --exec # actually spawn Turing
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime

BOT_DIR = Path.home() / ".openclaw" / "workspace" / "alter-bot-v1"
DATA_DIR = BOT_DIR / "data"
P0_ALERT_FILE = DATA_DIR / "p0_alerts.json"
STATE_FILE = DATA_DIR / "state.json"
CONFIG_FILE = BOT_DIR / "config.json"

EXEC_MODE = "--exec" in sys.argv
DRY_RUN = not EXEC_MODE

def load_json(path, default=None):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default if default is not None else {}

def get_recent_alerts(hours=2):
    """Get alerts from last N hours that haven't been processed."""
    alerts = load_json(P0_ALERT_FILE, [])
    cutoff = datetime.now().timestamp() - (hours * 3600)
    recent = []
    for a in alerts:
        try:
            ts = datetime.fromisoformat(a["timestamp"]).timestamp()
            if ts >= cutoff:
                recent.append(a)
        except Exception:
            pass
    return recent

def build_turing_prompt(alert):
    """Build a focused Turing prompt for a specific P0 issue."""
    alert_type = alert["type"]
    
    prompts = {
        "BALANCE_SAFETY": f"""Fix the alter-bot balance safety issue.

ALERT: Balance ${alert['balance']:.2f} below safety threshold ${alert['safety_threshold']}.
Current balance in state.json is dangerously low.

Actions needed:
1. IMMEDIATELY stop trading — set tier_1_only=true in config.json
2. Log the drawdown event
3. Review recent trades in fill_log.json to identify what went wrong
4. Check if circuit breakers were properly protecting the balance

Working directory: {BOT_DIR}
Bot file: {BOT_DIR}/bot_v2.py
Config: {CONFIG_FILE}
State: {STATE_FILE}

Report back what you found and what you fixed.""",

        "PORTFOLIO_DRAWDOWN": f"""Fix the alter-bot portfolio drawdown issue.

ALERT: Portfolio drawdown {alert['drawdown_pct']}% — peak ${alert['peak_balance']:.2f} → now ${alert['balance']:.2f}
This represents ${alert['peak_balance'] - alert['balance']:.2f} in paper losses.

Actions needed:
1. Check fill_log.json — identify the losing trades
2. Check slippage_log.json — were fills happening at bad prices?
3. Check city_error_history.json — were cities working correctly?
4. Determine if this is a signal quality issue or execution issue
5. Recommend config changes (avoid list, tier adjustments)

Working directory: {BOT_DIR}
Bot file: {BOT_DIR}/bot_v2.py
State: {STATE_FILE}

Report back what broke and what you're fixing.""",

        "CITY_CIRCUIT_BREAKER": f"""Fix city circuit breaker issues in alter-bot.

ALERT: Circuit breaker(s) triggered for: {', '.join(c['city'] for c in alert['tripped_cities'])}

Actions needed:
1. Check the city_data_error_count in state.json — which cities tripped?
2. Check city_error_history.json for the pattern of errors
3. Add affected cities to the avoid list in config.json
4. Verify the circuit breaker is properly persisting (not just in-memory)
5. Check if the city resolution fetcher is failing for specific cities

Working directory: {BOT_DIR}
Bot file: {BOT_DIR}/bot_v2.py
Config: {CONFIG_FILE}
State: {STATE_FILE}

Fix each city and report back.""",

        "ACTUAL_NULL_CASCADE": f"""Fix actual=0.0°C cascade issue in alter-bot.

ALERT: Cities with NULL/0 actual temps: {', '.join(c['city'] for c in alert['cascade_cities'])}

This means the resolution data source is returning NULL for actual temperatures.
The bot is recording actual=0.0 as if it's real data, corrupting win rate tracking.

Actions needed:
1. Check city_error_history.json — look for actual=0.0 entries in the cascade cities
2. Look at the self_improver.py fetch_actual_temp() function — is it returning 0 instead of None?
3. Find where NULL_TEMP_SENTINEL should be used but isn't
4. Fix the data path so NULL actuals are properly flagged as DATA_ERROR, not recorded as 0.0
5. Add affected cities to avoid list temporarily

Working directory: {BOT_DIR}
self_improver: {BOT_DIR}/self_improver.py
city_errors: {CITY_ERRORS_FILE}

Fix the data flow and report back.""",

        "AVOID_LIST_GAP": f"""Update alter-bot avoid list with problematic cities.

ALERT: Cities with errors not in avoid list: {', '.join(alert['missing_cities'])}

Actions needed:
1. Add these cities to the avoid list in config.json:
   {', '.join(alert['missing_cities'])}
2. Verify the avoid list is being read correctly in bot_v2.py (check should_scan_city())
3. After adding, restart the bot to pick up changes

Working directory: {BOT_DIR}
Config: {CONFIG_FILE}

Make the changes and verify syntax is valid.""",
    }
    
    return prompts.get(alert_type, f"Fix this P0 issue: {alert}")

def route_to_turing(alert):
    """Spawn a Turing sub-agent to fix a specific alert."""
    if DRY_RUN:
        print(f"  [DRY RUN] Would spawn Turing for: {alert['type']} — {alert['message']}")
        return True
    
    prompt = build_turing_prompt(alert)
    
    # Build the spawn command
    spawn_cmd = [
        sys.executable,  # python3
        "-c",
        f"""
import subprocess
result = subprocess.run(
    ['claude', '--permission-mode', 'bypassPermissions', '--print', {repr(prompt)}],
    cwd={repr(str(BOT_DIR))},
    capture_output=True,
    text=True
)
print(result.stdout)
if result.returncode != 0:
    print('ERROR:', result.stderr, file=sys.stderr)
"""
    ]
    
    try:
        import subprocess
        result = subprocess.run(
            ["claude", "--permission-mode", "bypassPermissions", "--print", prompt],
            cwd=str(BOT_DIR),
            capture_output=True,
            text=True,
            timeout=600
        )
        print(f"  [Turing done] {alert['type']}")
        print(f"  Output: {result.stdout[:500]}")
        if result.stderr:
            print(f"  Errors: {result.stderr[:200]}")
        return True
    except subprocess.TimeoutExpired:
        print(f"  [Turing TIMEOUT] {alert['type']} — exceeded 600s")
        return False
    except Exception as e:
        print(f"  [Turing ERROR] {alert['type']} — {e}")
        return False

def main():
    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}P0 Auto-Route — {datetime.now().isoformat()}")
    
    alerts = get_recent_alerts(hours=2)
    
    if not alerts:
        print("No recent P0 alerts to route. Exiting.")
        return
    
    print(f"Found {len(alerts)} P0 alert(s) to process")
    
    results = []
    for alert in alerts:
        severity = alert.get("severity", "P0")
        if severity != "P0":
            print(f"  Skipping {alert['type']} (severity={severity}, not P0)")
            continue
        
        print(f"\nRouting to Turing: {alert['type']}")
        print(f"  Message: {alert['message']}")
        success = route_to_turing(alert)
        results.append({
            "type": alert["type"],
            "success": success,
            "timestamp": alert["timestamp"]
        })
    
    # Summary
    successful = sum(1 for r in results if r["success"])
    print(f"\n{'[DRY RUN] ' if DRY_RUN else ''}Results: {successful}/{len(results)} routed successfully")
    
    if DRY_RUN:
        print("\nTo execute: python3 p0_autoroute.py --exec")

if __name__ == "__main__":
    main()