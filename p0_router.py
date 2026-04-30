#!/usr/bin/env python3
"""
p0_router.py — Alter-Bot Auto-Route Closed-Loop System

Polls p0_alerts.json + city_error_history.json for P0 conditions,
deduplicates via content hash, and spawns Turing to fix.

Plugin architecture: add new P0 types by adding dict entries to P0_PLUGINS.
No code changes needed beyond the plugin definition.
"""

import json
import hashlib
import logging
import os
import sys
import subprocess
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────
BOT_DIR = Path(__file__).parent
DATA_DIR = BOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"
FIXES_DIR = BOT_DIR / "fixes"

STATE_FILE     = DATA_DIR / "state.json"
P0_ALERTS_FILE = DATA_DIR / "p0_alerts.json"
CITY_ERRORS    = DATA_DIR / "city_error_history.json"
CONFIG_FILE     = BOT_DIR / "config.json"
PROCESSED_FILE = DATA_DIR / ".p0_processed.json"  # dedup: content hash → timestamp

# ──────────────────────────────────────────────────────────────
# LOGGING
# ──────────────────────────────────────────────────────────────
LOGS_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOGS_DIR / "p0_router.log"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger("p0_router")


# ──────────────────────────────────────────────────────────────
# HELPERS
# ──────────────────────────────────────────────────────────────

def load_json(path: Path, default=None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        log.warning(f"Failed to load {path}: {e}")
        return default if default is not None else {}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def content_hash(alert: dict) -> str:
    """Stable hash of alert content for dedup.
    Excludes timestamp fields (broken_at, processed_at, timestamp) to ensure
    the same alert type for the same city generates the same hash regardless of
    when it was generated.
    """
    # Fields to exclude from hash computation (timestamps that change per generation)
    exclude_keys = {"broken_at", "processed_at", "timestamp"}
    stable_alert = {k: v for k, v in alert.items() if k not in exclude_keys}
    canonical = json.dumps(stable_alert, sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def is_processed(alert: dict) -> bool:
    """Check if this exact alert has already been routed."""
    processed = load_json(PROCESSED_FILE, default=[])
    h = content_hash(alert)
    return h in [p.get("hash") for p in processed]


def mark_processed(alert: dict) -> None:
    """Record that we've routed this exact alert."""
    processed = load_json(PROCESSED_FILE, default=[])
    h = content_hash(alert)
    if h not in [p.get("hash") for p in processed]:
        processed.append({
            "hash": h,
            "alert": alert,
            "processed_at": datetime.now(timezone.utc).isoformat(),
        })
        # Keep last 200 entries
        processed = processed[-200:]
        save_json(PROCESSED_FILE, processed)


def load_config() -> dict:
    return load_json(CONFIG_FILE, default={})


def load_state() -> dict:
    return load_json(STATE_FILE, default={})


def get_us_cities() -> list:
    """US cities from config that have unit mismatch risk."""
    cfg = load_config()
    # Tier 1 + 2 US cities
    return ["Atlanta", "Dallas", "Houston", "Chicago", "Miami", "New York", "NYC",
            "Philadelphia", "Phoenix", "San Antonio", "San Diego", "Los Angeles"]


# ──────────────────────────────────────────────────────────────
# P0 CHECK FUNCTIONS
# Each returns list of alert dicts (empty = no alerts)
# ──────────────────────────────────────────────────────────────

def check_portfolio_drawdown() -> list:
    """
    Trigger: portfolio drawdown > 30% from peak.
    Reads p0_alerts.json for portfolio_drawdown entry.
    """
    alerts = load_json(P0_ALERTS_FILE, default=[])
    triggered = []
    for alert in alerts:
        # Handle both "portfolio_drawdown" (snake) and "PORTFOLIO_DRAWDOWN" (upper) type values
        alert_type = alert.get("type", "").lower().replace("_", "")
        if "portfoliodrawdown" in alert_type or alert.get("type") == "PORTFOLIO_DRAWDOWN":
            drawdown = alert.get("drawdown_pct", 0)
            if drawdown > 30:
                alert["plugin_id"] = "PORTFOLIO_DRAWDOWN"
                triggered.append(alert)
    return triggered


def check_us_unit_mismatch() -> list:
    """
    Trigger: US cities have °F actual vs °C forecast causing >20°C errors.
    Reads p0_alerts.json for us_unit_mismatch entries.
    """
    alerts = load_json(P0_ALERTS_FILE, default=[])
    triggered = []
    for alert in alerts:
        alert_type = str(alert.get("type", "")).lower()
        if "us_unit" in alert_type or "unitmismatch" in alert_type or alert.get("type") == "US_UNIT_MISMATCH":
            error = alert.get("error_celsius", 0)
            if error > 20:
                alert["plugin_id"] = "US_UNIT_MISMATCH"
                triggered.append(alert)
    return triggered


def check_circuit_breaker_candidates() -> list:
    """
    Trigger: City has 4+ DATA_ERRORs or circuit_broken=True in error history.
    Reads city_error_history.json.

    File structure: {"cities": {"city_name": {samples, win_rate, n_total, ...}}, "last_updated": ...}
    """
    try:
        error_data = load_json(CITY_ERRORS, default={})
        if not isinstance(error_data, dict):
            print(f"[CITY-CIRCUIT] {CITY_ERRORS} returned {type(error_data).__name__}, expected dict — skipping")
            return []
        cities_data = error_data.get("cities", {})
    except Exception as e:
        print(f"[CITY-CIRCUIT] Failed to load {CITY_ERRORS}: {e}")
        return []

    try:
        state = load_state()
        state_blocked = state.get("circuit_broken_cities", []) if isinstance(state, dict) else []
    except Exception as e:
        print(f"[CITY-CIRCUIT] Failed to load state: {e}")
        state_blocked = []

    try:
        with open(CONFIG_FILE, "r") as f:
            config = json.load(f)
        config_blocked = config.get("blocked_cities", []) if isinstance(config, dict) else []
    except Exception as e:
        print(f"[CITY-CIRCUIT] Failed to load config.json: {e}")
        config_blocked = []

    already_blocked = set(state_blocked) | set(config_blocked)
    triggered = []

    for city, info in cities_data.items():
        if not isinstance(info, dict):
            continue

        error_count = info.get("error_count", 0)
        circuit_broken = info.get("circuit_broken", False)
        win_rate = info.get("win_rate", 1.0)
        n_total = info.get("n_total", 0)
        avg_error = info.get("avg_error", 0.0)
        samples = info.get("samples", [])

        # Count DATA_ERRORs (samples with actual=0 or large spikes suggesting API failure)
        data_errors = sum(
            1 for s in samples
            if isinstance(s, dict) and (s.get("actual", 1) == 0 or s.get("error", 0) > 40)
        )

        # Skip cities already blocked in config or state — persistence is working, no alert needed
        if city in already_blocked:
            # Mark the appropriate alert as processed so subsequent runs don't re-alert
            if circuit_broken:
                mark_processed({
                    "type": "CITY_CIRCUIT_BROKEN",
                    "city": city,
                    "error_count": error_count,
                    "data_errors": data_errors,
                    "win_rate": win_rate,
                    "n_total": n_total,
                    "avg_error": avg_error,
                    "plugin_id": "CITY_POOR_PERFORMANCE",
                })
            elif data_errors >= 4:
                mark_processed({
                    "type": "CITY_DATA_ERROR_THRESHOLD",
                    "city": city,
                    "data_errors": data_errors,
                    "win_rate": win_rate,
                    "n_total": n_total,
                    "plugin_id": "CITY_POOR_PERFORMANCE",
                })
            elif n_total >= 20 and win_rate < 0.25:
                mark_processed({
                    "type": "CITY_LOW_WIN_RATE",
                    "city": city,
                    "win_rate": win_rate,
                    "n_total": n_total,
                    "avg_error": avg_error,
                    "plugin_id": "CITY_POOR_PERFORMANCE",
                })
            continue

        if circuit_broken:
            alert = {
                "type": "CITY_CIRCUIT_BROKEN",
                "city": city,
                "error_count": error_count,
                "data_errors": data_errors,
                "win_rate": win_rate,
                "n_total": n_total,
                "avg_error": avg_error,
                "plugin_id": "CITY_POOR_PERFORMANCE",
                "note": "Circuit broken in city_error_history — add to blocked_cities",
            }
            triggered.append(alert)
        elif data_errors >= 4:
            alert = {
                "type": "CITY_DATA_ERROR_THRESHOLD",
                "city": city,
                "data_errors": data_errors,
                "win_rate": win_rate,
                "n_total": n_total,
                "plugin_id": "CITY_POOR_PERFORMANCE",
                "note": "4+ DATA_ERRORs (actual=0 or >40°C error) — circuit breaker should fire",
            }
            triggered.append(alert)
        elif n_total >= 20 and win_rate < 0.25:
            # Persistent poor performance: 20+ samples, <25% win rate
            # DEFENSIVE FIX: if city is circuit_broken in city_error_history, skip.
            # This guards against race conditions where persistence updated city_error_history
            # but the city hasn't been added to already_blocked yet.
            if info.get("circuit_broken"):
                continue
            alert = {
                "type": "CITY_LOW_WIN_RATE",
                "city": city,
                "win_rate": win_rate,
                "n_total": n_total,
                "avg_error": avg_error,
                "plugin_id": "CITY_POOR_PERFORMANCE",
                "note": f"{n_total}+ samples with {win_rate*100:.0f}% win rate — add to blocked_cities",
            }
            triggered.append(alert)

    return triggered


def check_ev_formula() -> list:
    """
    Trigger: EV formula uses `p - price` instead of proper Kelly-based formula.
    Reads p0_alerts.json for ev_formula_error.
    """
    alerts = load_json(P0_ALERTS_FILE, default=[])
    triggered = []
    for alert in alerts:
        alert_type = str(alert.get("type", "")).lower()
        if "ev_formula" in alert_type or alert.get("type") == "EV_FORMULA_ERROR":
            alert["plugin_id"] = "EV_FORMULA_WRONG"
            triggered.append(alert)
    return triggered


def check_whale_skip_tracking() -> list:
    """
    Trigger: whale_skip_reason printed but not stored/emitted.

    Checks whale_skips.jsonl directly AND city_error_history.json for whale_skip
    samples. Only fires an alert if we have EVIDENCE that whale skips occurred
    but weren't captured (e.g., whale_skip samples in city_error_history but no
    entries in whale_skips.jsonl). False positive when no whale skips have
    happened yet is suppressed.
    """
    triggered = []
    whale_log = LOGS_DIR / "whale_skips.jsonl"

    # Count entries in whale_skips.jsonl
    whale_log_entries = []
    if whale_log.exists():
        with open(whale_log) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    whale_log_entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    # Count whale_skip samples in city_error_history
    city_error_entries = []
    city_errors_file = DATA_DIR / "city_error_history.json"
    if city_errors_file.exists():
        try:
            ce_data = load_json(city_errors_file, default={"cities": {}})
            for city, city_data in ce_data.get("cities", {}).items():
                for sample in city_data.get("samples", []):
                    if sample.get("whale_skip"):
                        city_error_entries.append(sample)
        except Exception:
            pass

    # If either source has whale skip entries, they ARE being captured — no alert
    if len(whale_log_entries) > 0 or len(city_error_entries) > 0:
        log.info(f"[WHALE_SKIP] {len(whale_log_entries)} log entries, {len(city_error_entries)} city_error entries — tracking OK")
        return triggered

    # Neither source has whale skip entries — this is a false positive.
    # No whale skips have occurred yet. Do NOT fire an alert.
    log.info("[WHALE_SKIP] No whale skip entries in whale_skips.jsonl or city_error_history — no whale skips have occurred (not a bug)")
    return triggered


# ──────────────────────────────────────────────────────────────
# PLUGIN REGISTRY
# ──────────────────────────────────────────────────────────────
# Adding a new P0 type = add one dict entry, no code changes needed.

P0_PLUGINS = [
    {
        "id": "PORTFOLIO_DRAWDOWN",
        "name": "Portfolio Drawdown >30%",
        "severity": "P0",
        "check_fn": check_portfolio_drawdown,
        "manifest": "portfolio_drawdown.md",
        "enabled": True,
    },
    {
        "id": "US_UNIT_MISMATCH",
        "name": "US City Unit Mismatch",
        "severity": "P0",
        "check_fn": check_us_unit_mismatch,
        "manifest": "us_unit_fix.md",
        "enabled": True,
    },
    {
        "id": "CITY_POOR_PERFORMANCE",
        "name": "City Circuit Breaker / Poor Performance",
        "severity": "P0",
        "check_fn": check_circuit_breaker_candidates,
        "manifest": "city_circuit_breaker.md",
        "enabled": True,
    },
    {
        "id": "EV_FORMULA_WRONG",
        "name": "EV Formula Calculation Error",
        "severity": "P1",
        "check_fn": check_ev_formula,
        "manifest": "ev_formula_fix.md",
        "enabled": True,
    },
    {
        "id": "WHALE_SKIP_NOT_CAPTURED",
        "name": "Whale Skip Reason Not Tracked",
        "severity": "P1",
        "check_fn": check_whale_skip_tracking,
        "manifest": "whale_skip_untracked.md",
        "enabled": True,
    },
]


# ──────────────────────────────────────────────────────────────
# INDEX.MD — list all active P0s and status
# ──────────────────────────────────────────────────────────────

def write_index(alerts_by_plugin: dict, total_routed: int) -> None:
    """Generate fixes/INDEX.md with all active P0s and their status."""
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    lines = [
        "# Alter-Bot P0 Fix Index",
        "",
        f"Generated: {now}",
        f"Total alerts routed to Turing: {total_routed}",
        "",
        "## Plugin Registry",
        "",
        "| ID | Name | Severity | Enabled |",
        "|----|------|----------|---------|",
    ]

    for plugin in P0_PLUGINS:
        enabled = "✅" if plugin["enabled"] else "❌"
        lines.append(f"| `{plugin['id']}` | {plugin['name']} | {plugin['severity']} | {enabled} |")

    lines += ["", "## Active Alerts", "",]

    if alerts_by_plugin:
        for plugin_id, alerts in alerts_by_plugin.items():
            if alerts:
                plugin_name = next((p["name"] for p in P0_PLUGINS if p["id"] == plugin_id), plugin_id)
                lines.append(f"### {plugin_name} (`{plugin_id}`)")
                for alert in alerts:
                    lines.append(f"- `{alert.get('type')}` — city: `{alert.get('city', 'N/A')}` "
                                 f"| errors: `{alert.get('error_count', alert.get('error_celsius', 'N/A'))}` "
                                 f"| note: {alert.get('note', alert.get('reason', 'N/A'))}")
                lines.append("")
    else:
        lines.append("*No active P0 alerts.*\n")

    lines += [
        "## Architecture",
        "",
        "Each P0 type is a **plugin** in `P0_PLUGINS`. To add a new P0 type:",
        "1. Write a fix manifest in `fixes/<name>.md`",
        "2. Add a `check_fn` that returns alert dicts",
        "3. Add one dict entry to `P0_PLUGINS` — no other code changes needed",
        "",
    ]

    index_path = FIXES_DIR / "INDEX.md"
    index_path.write_text("\n".join(lines), encoding="utf-8")
    log.info(f"Index written: {index_path}")


# ──────────────────────────────────────────────────────────────
# SPAWN TURING
# ──────────────────────────────────────────────────────────────

def spawn_turing(alert: dict, plugin: dict, dry_run: bool = False) -> bool:
    """
    Spawn Turing (Claude Code) with fix manifest context.
    Returns True if spawn was triggered, False otherwise.
    If dry_run=True, logs the full context but does NOT spawn hermes.
    """
    manifest_path = FIXES_DIR / plugin["manifest"]
    if not manifest_path.exists():
        log.error(f"Manifest not found: {manifest_path}")
        return False

    manifest_content = manifest_path.read_text(encoding="utf-8")

    # Build full context for Turing
    context = f"""\
# P0 ALERT — AUTO-ROUTED TO TURING

## Alert Metadata
- **Plugin ID:** {plugin['id']}
- **Plugin Name:** {plugin['name']}
- **Severity:** {plugin['severity']}
- **Timestamp:** {datetime.now(timezone.utc).isoformat()}
- **Alert Type:** {alert.get('type')}
- **City:** {alert.get('city', 'N/A')}

## Alert Details (full dump)
```json
{json.dumps(alert, indent=2, default=str)}
```

## Fix Manifest (from fixes/{plugin['manifest']})
```markdown
{manifest_content}
```

## Bot Context
- Bot directory: {BOT_DIR}
- Main bot: {BOT_DIR}/bot_v2.py
- Self-improver: {BOT_DIR}/self_improver.py
- State: {STATE_FILE}
- Config: {CONFIG_FILE}

## Your Task
Read the fix manifest above. It contains:
1. Root cause analysis
2. Exact file:function locations to fix
3. Code changes required
4. Verify steps

Fix the issue in bot_v2.py (or self_improver.py if specified).
After fixing, run `python3 p0_router.py` to verify no new P0 alerts appear.

IMPORTANT: 
- Fix must be verified (run tests / paper trade cycle)
- Log what you changed and what you verified
- Do NOT modify P0_PLUGINS or p0_router.py unless the manifest requires it
"""

    # Write context to a temp file for hermes
    task_file = LOGS_DIR / f"p0_task_{int(time.time())}.txt"
    task_file.write_text(context, encoding="utf-8")

    log.info(f"[TURING] Spawning for {plugin['id']} — {alert.get('type')} — city={alert.get('city','N/A')}")
    log.info(f"[TURING] Context written to: {task_file}")
    log.info(f"[TURING] Manifest: {manifest_path.name}")
    log.info(f"[TURING] Alert summary: {json.dumps(alert, default=str)[:200]}...")

    if dry_run:
        log.info(f"[TURING] DRY RUN — would spawn hermes now")
        return True

    try:
        cmd = [
            "claude",
            "--print",
            f"Fix this P0 alert. Read {task_file} for full context.",
            "--permission-mode", "bypassPermissions",
        ]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=900,
        )
        log.info(f"[TURING] hermes stdout: {result.stdout[:500] if result.stdout else 'none'}")
        if result.stderr:
            log.warning(f"[TURING] hermes stderr: {result.stderr[:500]}")
        log.info(f"[TURING] hermes return code: {result.returncode}")
        return True

    except subprocess.TimeoutExpired:
        log.error("[TURING] hermes timed out after 900s")
        return False
    except Exception as e:
        log.error(f"[TURING] Failed to spawn hermes: {e}")
        return False


# ──────────────────────────────────────────────────────────────
# MAIN RUN
# ──────────────────────────────────────────────────────────────

def run() -> dict:
    """
    Run one cycle: check all plugins, route new P0s to Turing.
    Returns dict of {plugin_id: [alerts]} for active alerts.
    """
    log.info("=" * 60)
    log.info(f"p0_router run started — {datetime.now(timezone.utc).isoformat()}")
    log.info("=" * 60)

    # Track state
    total_routed = 0
    alerts_by_plugin: dict[str, list] = {p["id"]: [] for p in P0_PLUGINS}
    new_alerts = []

    for plugin in P0_PLUGINS:
        if not plugin["enabled"]:
            log.debug(f"Plugin {plugin['id']} disabled — skipping")
            continue

        plugin_id = plugin["id"]
        check_fn = plugin["check_fn"]

        try:
            alerts = check_fn()
        except Exception as e:
            log.error(f"[{plugin_id}] Check function failed: {e}")
            alerts = []

        log.info(f"[{plugin_id}] Found {len(alerts)} alert(s)")

        for alert in alerts:
            # Dedup
            if is_processed(alert):
                log.info(f"[{plugin_id}] Dedup — already processed: {alert.get('type')} city={alert.get('city')}")
                alerts_by_plugin[plugin_id].append(alert)
                continue

            # New alert — route to Turing
            log.info(f"[{plugin_id}] NEW ALERT — routing to Turing: {json.dumps(alert, default=str)[:200]}")
            success = spawn_turing(alert, plugin, dry_run=DRY_RUN)
            if success:
                new_alerts.append(alert)
                if not DRY_RUN:
                    mark_processed(alert)
                    total_routed += 1
                else:
                    log.info(f"[{plugin_id}] DRY RUN — not marking processed, not counting as routed")
            alerts_by_plugin[plugin_id].append(alert)

    # Write/update INDEX.md
    write_index(alerts_by_plugin, total_routed)

    log.info("=" * 60)
    log.info(f"Run complete — {len(new_alerts)} new alerts routed, {total_routed} total routed")
    log.info(f"Index: {FIXES_DIR / 'INDEX.md'}")
    log.info("=" * 60)

    return {
        "new_alerts": new_alerts,
        "alerts_by_plugin": alerts_by_plugin,
        "total_routed": total_routed,
    }


DRY_RUN = "--dry-run" in sys.argv

if __name__ == "__main__":
    if DRY_RUN:
        print("[DRY RUN] Checking alerts only — will NOT spawn Turing")
    result = run()
    new_count = len(result["new_alerts"])
    if new_count == 0:
        print("No new P0 alerts — all clear.")
    else:
        mode = "[DRY RUN] Would route" if DRY_RUN else "New P0 alerts routed"
        print(f"{mode}: {new_count}")
        for alert in result["new_alerts"]:
            print(f"  - {alert.get('plugin_id')}: {alert.get('type')} city={alert.get('city', 'N/A')}")
