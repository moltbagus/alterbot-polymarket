#!/usr/bin/env python3
"""
Alter-Bot Proactive Monitoring Agent
=====================================
Runs every 30 minutes. Checks bot health, performance, and known issues.
Sends Telegram alert only if action needed. Silent OK otherwise.

Usage:
    python3 ~/.openclaw/workspace/alter-bot-v1/monitoring/monitor_agent.py
"""

import sys
import json
import subprocess
import re
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE    = Path.home() / ".openclaw" / "workspace"
ALTERBOT_DIR = WORKSPACE / "alter-bot-v1"
DATA_DIR     = ALTERBOT_DIR / "data"
STATE_FILE   = DATA_DIR / "state.json"
FILL_LOG     = DATA_DIR / "fill_log.json"
PM2_LOG      = Path.home() / ".pm2" / "logs" / "alter-bot-v2-out-0.log"
TELEGRAM_TARGET = "392076648"

# ─── Human Checkpoint Config ──────────────────────────────
CHECKPOINT_CONFIG = {
    "consecutive_losses_threshold": 4,      # Pause after 4 consecutive losses
    "drawdown_threshold_pct": 30.0,        # Pause after 30% drawdown from peak
    "checkpoint_file": DATA_DIR / ".checkpoint",  # Persisted so it survives restarts
}

# ─── Issue Signatures ────────────────────────────────────
US_CITIES = ["new-york", "chicago", "denver", "atlanta", "miami", "los-angeles", "houston", "seattle", "dallas"]

def read_state():
    if not STATE_FILE.exists():
        return None
    return json.loads(STATE_FILE.read_text())

def read_fills(n=10):
    if not FILL_LOG.exists():
        return []
    try:
        fills = json.loads(FILL_LOG.read_text())
        return fills[-n:]
    except Exception:
        return []

def read_fills_all():
    """Read all fills for consecutive loss analysis (up to last 20)."""
    if not FILL_LOG.exists():
        return []
    try:
        fills = json.loads(FILL_LOG.read_text())
        return fills[-20:]
    except Exception:
        return []

# ─── Checkpoint Functions ─────────────────────────────────

def read_checkpoint():
    """Read checkpoint state from data/.checkpoint. Returns dict with active, reason, trigger_value, timestamp."""
    cp_file = CHECKPOINT_CONFIG["checkpoint_file"]
    if not cp_file.exists():
        return {"active": False, "reason": "", "trigger_value": 0.0, "timestamp": ""}
    try:
        return json.loads(cp_file.read_text())
    except Exception:
        return {"active": False, "reason": "", "trigger_value": 0.0, "timestamp": ""}

def write_checkpoint(info: dict):
    """Write checkpoint state to data/.checkpoint. Creates parent dirs if needed."""
    cp_file = CHECKPOINT_CONFIG["checkpoint_file"]
    cp_file.parent.mkdir(parents=True, exist_ok=True)
    cp_file.write_text(json.dumps(info, indent=2))

def check_consecutive_losses(state, fills):
    """
    Count consecutive losses by walking fills in reverse chronological order.
    A 'consecutive loss' = fill where outcome == 'loss' OR pnl < 0.
    Returns (triggered: bool, reason: str, loss_count: int).
    """
    if not fills:
        return False, "", 0

    threshold = CHECKPOINT_CONFIG["consecutive_losses_threshold"]

    # Walk fills in reverse (most recent first)
    loss_count = 0
    for fill in reversed(fills):
        outcome = fill.get("outcome", "")
        pnl = fill.get("pnl", None)
        if outcome == "loss" or (pnl is not None and pnl < 0):
            loss_count += 1
        else:
            # Hit a non-loss fill — stop counting
            break

    if loss_count >= threshold:
        reason = f"consecutive_losses"
        return True, reason, loss_count
    return False, "", 0

def check_drawdown(state):
    """
    Compute drawdown from peak_balance vs current balance.
    Returns (triggered: bool, reason: str, drawdown_pct: float).
    """
    if not state:
        return False, "", 0.0

    balance = state.get("balance", 0)
    peak_balance = state.get("peak_balance", balance)

    if peak_balance <= 0:
        return False, "", 0.0

    drawdown_pct = (peak_balance - balance) / peak_balance * 100
    threshold = CHECKPOINT_CONFIG["drawdown_threshold_pct"]

    if drawdown_pct >= threshold:
        reason = f"drawdown"
        return True, reason, drawdown_pct
    return False, "", 0.0

def send_checkpoint_alert(reason: str, value: float):
    """Send a human checkpoint alert to Telegram."""
    if reason == "consecutive_losses":
        value_str = f"{int(value)} consecutive losses"
    elif reason == "drawdown":
        value_str = f"{value:.1f}% drawdown from peak"
    else:
        value_str = f"{value}"

    msg = (
        "🛑 ALTER-BOT CHECKPOINT TRIGGERED\n"
        f"Reason: {value_str}\n"
        f"Bot has PAUSED trading.\n"
        "Reply YES to this message on Telegram to resume trading.\n"
        "Bot will NOT trade until you confirm."
    )
    send_telegram(msg)

def resume_checkpoint():
    """Clear the checkpoint — allow trading to resume."""
    write_checkpoint({
        "active": False,
        "reason": "",
        "trigger_value": 0.0,
        "timestamp": datetime.now(timezone.utc).isoformat()
    })
    msg = (
        "✅ ALTER-BOT RESUMED\n"
        "Checkpoint cleared — bot is trading again.\n"
        "Monitor will continue as normal."
    )
    send_telegram(msg)
    print("[CHECKPOINT] Cleared — trading resumed")

# ─── PM2 / Health Checks ──────────────────────────────────

def check_pm2_status():
    # Returns restarts, uptime, status from pm2 describe
    try:
        out = subprocess.run(["pm2", "describe", "alter-bot-v2"],
                          capture_output=True, text=True, timeout=10)
        stdout = out.stdout
        # More flexible pattern: restarts followed by any non-digit chars then digits
        restarts_m = re.search(r'restarts\s+\D+(\d+)', stdout)
        status_m = re.search(r'status\s+\D+(\w+)', stdout)
        restarts = int(restarts_m.group(1)) if restarts_m else None
        status = status_m.group(1) if status_m else "?"
        return restarts, None, status
    except Exception:
        return None, None, None

def check_pm2_errors(n=30):
    # Check PM2 logs for ERROR lines in last n lines.
    try:
        out = subprocess.run(["pm2", "logs", "alter-bot-v2", "--lines", str(n), "--nostream"],
                          capture_output=True, text=True, timeout=10)
        errors = [l for l in out.stdout.splitlines() if "ERROR" in l.upper() or "error" in l.lower()]
        return errors
    except Exception:
        return []

def analyze_fills(fills):
    # Analyze recent fills for fill rate and EV quality.
    # Win rate requires actual resolution data - not available in fill_log alone.
    if not fills:
        return {"count": 0, "filled": 0, "partial": 0, "avg_ev": 0, "us_city_fills": 0, "total_slippage_pct": 0}

    filled = sum(1 for f in fills if f.get("filled"))
    partial = sum(1 for f in fills if not f.get("filled") and f.get("size_filled", 0) > 0)
    avg_ev = sum(f.get("ev", 0) for f in fills) / len(fills) if fills else 0
    us_city_fills = sum(1 for f in fills if f.get("city") in US_CITIES)
    total_slippage_pct = sum(f.get("slippage_pct", 0) for f in fills) / len(fills) if fills else 0

    return {
        "count": len(fills),
        "filled": filled,
        "partial": partial,
        "avg_ev": avg_ev,
        "us_city_fills": us_city_fills,
        "total_slippage_pct": total_slippage_pct,
    }

def check_circuit_breakers(state):
    # Check if any cities are circuit-broken.
    broken = state.get("circuit_broken", []) if state else []
    return broken

def compose_report(state, fills, fill_stats, restarts, broken_cities):
    # Compose Telegram report.
    balance = state.get("balance", 0) if state else 0
    starting = state.get("starting_balance", 1000) if state else 1000
    total_trades = state.get("total_trades", 0) if state else 0
    wins = state.get("wins", 0) if state else 0
    losses = state.get("losses", 0) if state else 0
    session_pnl = balance - starting
    session_pct = (session_pnl / starting * 100) if starting else 0
    win_rate = wins / (wins + losses) if (wins + losses) > 0 else 0

    issues = []

    # 1. US city unit mismatch check
    if fill_stats.get("us_city_fills", 0) > 0:
        issues.append("US city fills detected (unit mismatch UNFIXED)")

    # 2. PM2 restart check
    if restarts and restarts > 10:
        issues.append(f"PM2 restarts: {restarts} (>10 = unstable)")

    # 3. Win rate degradation (from state.json, which tracks resolved trades)
    if (wins + losses) >= 5:
        if win_rate < 0.40:
            issues.append(f"Win rate degraded: {win_rate:.0%} ({wins}W/{losses}L)")

    # 4. Circuit breaker active
    if broken_cities:
        issues.append(f"Circuit broken: {', '.join(broken_cities)}")

    # 5. EV quality check
    avg_ev = fill_stats.get("avg_ev", 0)
    if avg_ev < 0.10 and fill_stats.get("count", 0) >= 3:
        issues.append(f"Low EV: {avg_ev:.3f} avg (last {fill_stats['count']} fills)")

    # 6. High slippage check
    slip = fill_stats.get("total_slippage_pct", 0)
    if slip > 0.12 and fill_stats.get("count", 0) >= 3:
        issues.append(f"High slippage: {slip:.1%} avg")

    # 7. Balance drawdown
    if session_pct < -30:
        issues.append(f"Balance drawdown: {session_pct:.1f}% from peak")

    # Compose message
    msg_lines = [
        f"ALTER-BOT MONITOR | {datetime.now().strftime('%H:%M MYT')}",
        f"Balance: ${balance:.2f} ({session_pnl:+.2f} {session_pct:+.1f}%)",
        f"Trades: {total_trades} total | {wins}W/{losses}L",
        f"Last {fill_stats['count']} fills: {fill_stats['filled']} filled, {fill_stats['partial']} partial | Avg EV: {avg_ev:.3f}",
        f"PM2 restarts: {restarts or '?'} | Slip: {slip:.1%}",
    ]

    if issues:
        msg_lines.append("")
        for issue in issues:
            msg_lines.append(f"  - {issue}")
        msg_lines.append("")
        msg_lines.append("Action required — see execplan/ALTER-BOT-MONITORING.md")
        return "\n".join(msg_lines), True
    else:
        msg_lines.append("")
        msg_lines.append("All clear — bot healthy")
        return "\n".join(msg_lines), False

def send_telegram(msg):
    # Send Telegram message via openclaw.
    try:
        subprocess.run([
            "openclaw", "message", "send",
            "--channel", "telegram",
            "--target", TELEGRAM_TARGET,
            "--message", msg
        ], capture_output=True, timeout=20)
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)

def main():
    # 0. Check if a checkpoint is already active — if so, silent OK
    checkpoint = read_checkpoint()
    if checkpoint.get("active"):
        print(f"[CHECKPOINT ACTIVE] {checkpoint['reason']} — awaiting Colbert's YES")
        return 0  # Silent, don't send alerts again

    # 1. Read state
    state = read_state()

    # 2. Read fills (last 20 for consecutive loss analysis)
    fills = read_fills_all()
    fill_stats = analyze_fills(fills[-10:] if fills else [])  # last 10 for stats

    # 3. PM2 status
    restarts, _, status = check_pm2_status()

    # 4. Circuit breakers
    broken = check_circuit_breakers(state)

    # 5. ── Checkpoint Detection ─────────────────────────────
    # Run checkpoint checks AFTER existing health checks
    consec_triggered, consec_reason, consec_count = check_consecutive_losses(state, fills)
    draw_triggered, draw_reason, draw_pct = check_drawdown(state)

    checkpoint_triggered = False
    checkpoint_reason = ""
    checkpoint_value = 0.0

    if consec_triggered:
        checkpoint_triggered = True
        checkpoint_reason = consec_reason
        checkpoint_value = float(consec_count)
    elif draw_triggered:
        checkpoint_triggered = True
        checkpoint_reason = draw_reason
        checkpoint_value = draw_pct

    if checkpoint_triggered:
        write_checkpoint({
            "active": True,
            "reason": checkpoint_reason,
            "trigger_value": checkpoint_value,
            "timestamp": datetime.now(timezone.utc).isoformat()
        })
        send_checkpoint_alert(checkpoint_reason, checkpoint_value)
        # Continue to compose and print report, but return 1 to escalate

    # 6. Compose report
    report, has_issues = compose_report(state, fills[-10:] if fills else [], fill_stats, restarts, broken)

    # 7. Print to stdout
    print(report)

    # 8. Send to Telegram if issues found
    if has_issues:
        send_telegram(report)
    else:
        print("[SILENT OK — no Telegram sent]")

    # Return 1 if checkpoint triggered (escalate to heartbeat)
    return 0 if not checkpoint_triggered else 1

if __name__ == "__main__":
    sys.exit(main())