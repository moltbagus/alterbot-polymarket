#!/usr/bin/env python3
"""
p0_alert_detector.py — Alter-Bot P0 Alert Detection

Scans whale_skips.jsonl and other data sources for P0 conditions,
writes findings to p0_alerts.json for p0_router to consume.
"""

import hashlib
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ──────────────────────────────────────────────────────────────
# PATHS
# ──────────────────────────────────────────────────────────────
BOT_DIR = Path(__file__).parent
DATA_DIR = BOT_DIR / "data"
LOGS_DIR = DATA_DIR / "logs"

WHALE_SKIP_LOG = LOGS_DIR / "whale_skips.jsonl"
P0_ALERTS_FILE = DATA_DIR / "p0_alerts.json"


def load_json(path: Path, default=None) -> Any:
    if not path.exists():
        return default if default is not None else {}
    try:
        with open(path) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError) as e:
        print(f"[WARN] Failed to load {path}: {e}")
        return default if default is not None else {}


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, default=str)


def load_whale_skips() -> list[dict]:
    """Read all entries from whale_skips.jsonl."""
    if not WHALE_SKIP_LOG.exists():
        return []
    entries = []
    with open(WHALE_SKIP_LOG) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entries.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return entries


def get_existing_p0_hashes() -> set[str]:
    """Get hashes of already-existing p0_alerts to avoid duplicates."""
    existing = load_json(P0_ALERTS_FILE, default=[])
    if not isinstance(existing, list):
        return set()
    hashes = set()
    for alert in existing:
        if isinstance(alert, dict) and "hash" in alert:
            hashes.add(alert["hash"])
    return hashes


def make_hash(entry: dict) -> str:
    """Make a stable hash for a whale skip entry."""
    key_parts = [
        entry.get("city", ""),
        entry.get("date", ""),
        entry.get("whale_reason", ""),
    ]
    return hashlib.sha256(json.dumps(key_parts, sort_keys=True).encode()).hexdigest()[:16]


def check_whale_skip_tracking() -> list[dict]:
    """
    Check if whale skips are being captured and routed properly.
    Reads whale_skips.jsonl and generates P0 alerts for new entries.
    """
    entries = load_whale_skips()
    if not entries:
        return []

    existing_hashes = get_existing_p0_hashes()
    new_alerts = []

    for entry in entries:
        alert = {
            "type": "WHALE_SKIP_CAPTURED",
            "city": entry.get("city"),
            "whale_reason": entry.get("whale_reason"),
            "timestamp": entry.get("timestamp"),
            "forecast": entry.get("forecast"),
            "price": entry.get("price"),
            "severity": "P2",
            "hash": make_hash(entry),
        }
        if alert["hash"] not in existing_hashes:
            new_alerts.append(alert)

    return new_alerts


def detect_all() -> list[dict]:
    """
    Run all P0 detection checks.
    Returns list of new alerts to append to p0_alerts.json.
    """
    all_alerts = []

    # Check whale skip tracking
    whale_alerts = check_whale_skip_tracking()
    all_alerts.extend(whale_alerts)

    return all_alerts


def main():
    print(f"[p0_alert_detector] Starting scan at {datetime.now(timezone.utc).isoformat()}")

    new_alerts = detect_all()

    if not new_alerts:
        print("[p0_alert_detector] No new P0 conditions detected")
        return

    # Load existing p0_alerts
    existing = load_json(P0_ALERTS_FILE, default=[])
    if not isinstance(existing, list):
        existing = []

    # Append new alerts
    existing.extend(new_alerts)

    # Save
    save_json(P0_ALERTS_FILE, existing)

    print(f"[p0_alert_detector] Added {len(new_alerts)} new alert(s) to p0_alerts.json")
    for a in new_alerts:
        print(f"  - [{a['type']}] {a.get('city')} | {a.get('whale_reason')} | severity={a.get('severity')}")


if __name__ == "__main__":
    main()
