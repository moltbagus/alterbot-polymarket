#!/usr/bin/env python3
"""
Alter-Bot-V2 Runner — OpenClaw Integration Layer
================================================
Bridges HermesAgent (OpenClaw) to bot_v2.py via PM2.

Usage:
    python runner.py status    → structured JSON status
    python runner.py start     → pm2 start + return PID
    python runner.py stop      → pm2 stop
    python runner.py restart   → pm2 restart
    python runner.py monitor   → daily monitor report (for cron)
    python runner.py report    → full trading report
    python runner.py logs      → last 30 lines of PM2 logs
"""

import json
import subprocess
import sys
from pathlib import Path

BOT_DIR = Path("/home/alyssa/.openclaw/workspace/alter-bot-v1")
ECOSYSTEM = BOT_DIR / "alter-bot-ecosystem.config.js"
PM2_NAME = "alter-bot-v2"
DATA_DIR = BOT_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
FILL_LOG = DATA_DIR / "fill_log.json"


def pm2_cmd(cmd: str) -> tuple[str, int]:
    """Run a pm2 command, return (output, exit_code)."""
    result = subprocess.run(
        ["pm2"] + cmd.split(),
        capture_output=True,
        text=True,
    )
    return result.stdout.strip(), result.returncode


def get_pm2_status() -> dict:
    """Get PM2 process status."""
    out, code = pm2_cmd(f"jlist {PM2_NAME}")
    if code != 0 or not out:
        return {"running": False, "pm2_status": "not_found"}
    try:
        processes = json.loads(out)
        if not processes:
            return {"running": False, "pm2_status": "not_found"}
        p = processes[0]
        return {
            "running": p.get("pm2_env", {}).get("status") == "online",
            "pm2_status": p.get("pm2_env", {}).get("status"),
            "pid": p.get("pid"),
            "uptime": p.get("pm2_env", {}).get("pm_uptime"),
            "memory": p.get("monit", {}).get("memory"),
            "cpu": p.get("monit", {}).get("cpu"),
            "restarts": p.get("pm2_env", {}).get("restart_time", 0),
            "created_at": p.get("created_at"),
        }
    except (json.JSONDecodeError, KeyError, IndexError):
        return {"running": False, "pm2_status": "parse_error", "raw": out[:200]}


def get_bot_status() -> dict:
    """Run bot_v2.py status and parse output."""
    result = subprocess.run(
        ["python3", "bot_v2.py", "status"],
        capture_output=True,
        text=True,
        cwd=str(BOT_DIR),
    )
    status = {"raw": result.stdout.strip()}
    for line in result.stdout.strip().split("\n"):
        line = line.strip()
        if "Balance:" in line:
            try:
                status["balance"] = float(line.split("$")[-1].replace(",", ""))
            except ValueError:
                status["balance_raw"] = line
        elif "Trades:" in line:
            parts = line.split("|")
            if len(parts) >= 3:
                try:
                    total = int(parts[0].split()[-1])
                    wins = int(parts[1].split()[-1].replace("W:", ""))
                    losses = int(parts[2].split()[-1].replace("L:", ""))
                    status["trades"] = {"total": total, "wins": wins, "losses": losses}
                except (ValueError, IndexError):
                    pass
        elif "Open:" in line:
            try:
                status["open_positions"] = int(line.split()[-1])
            except ValueError:
                pass
        elif "Resolved:" in line:
            try:
                status["resolved"] = int(line.split()[-1])
            except ValueError:
                pass
    return status


def get_trading_state() -> dict:
    """Read state.json for persisted trading state."""
    if not STATE_FILE.exists():
        return {}
    try:
        with open(STATE_FILE) as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def cmd_status() -> dict:
    """Return full status: PM2 + bot + trading state."""
    pm2 = get_pm2_status()
    bot = get_bot_status()
    state = get_trading_state()

    result = {
        "pm2": pm2,
        "bot": bot,
        "trading": state,
    }

    # Add Polymarket market availability
    result["polymarket_markets"] = check_polymarket_markets()

    return result


def check_polymarket_markets() -> dict:
    """Check if Polymarket temperature markets are available."""
    import requests

    try:
        resp = requests.get(
            "https://clob.polymarket.com/markets?closed=false&limit=100",
            headers={"Content-Type": "application/json"},
            timeout=10,
        )
        raw = resp.json()
        # API returns {"data": [...]} not direct array
        markets = raw.get("data", raw) if isinstance(raw, dict) else raw
        temp_keywords = ["temperature", "°c", "°f", "weather", "heat", "cold", "snow", "rain"]
        temp_markets = [
            m for m in markets
            if isinstance(m, dict) and any(
                kw in m.get("question", "").lower()
                for kw in temp_keywords
            )
        ]
        return {
            "available": len(temp_markets) > 0,
            "count": len(temp_markets),
            "samples": [m.get("question", "")[:80] for m in temp_markets[:3]],
        }
    except Exception as e:
        return {"available": False, "error": str(e)}


def cmd_start() -> dict:
    """Start the bot via PM2."""
    if get_pm2_status()["running"]:
        pid = get_pm2_status()["pid"]
        return {"started": False, "already_running": True, "pid": pid}

    out, code = pm2_cmd(f"start {ECOSYSTEM}")
    if code == 0:
        pm2 = get_pm2_status()
        return {"started": True, "pid": pm2.get("pid"), "output": out}
    return {"started": False, "error": out}


def cmd_stop() -> dict:
    """Stop the bot via PM2."""
    out, code = pm2_cmd(f"stop {PM2_NAME}")
    return {"stopped": code == 0, "output": out}


def cmd_restart() -> dict:
    """Restart the bot via PM2."""
    out, code = pm2_cmd(f"restart {PM2_NAME}")
    if code == 0:
        pm2 = get_pm2_status()
        return {"restarted": True, "pid": pm2.get("pid"), "output": out}
    return {"restarted": False, "error": out}


def cmd_logs(lines: int = 30) -> dict:
    """Get PM2 logs."""
    out, _ = pm2_cmd(f"logs {PM2_NAME} --lines {lines} --nostream")
    err, _ = pm2_cmd(f"logs {PM2_NAME} --lines {lines} --nostream --err")
    return {"stdout": out[-3000:], "stderr": err[-1000:]}


def cmd_report() -> dict:
    """Get full trading report from bot."""
    result = subprocess.run(
        ["python3", "bot_v2.py", "report"],
        capture_output=True,
        text=True,
        cwd=str(BOT_DIR),
    )
    return {"report": result.stdout.strip(), "errors": result.stderr.strip()[-500:]}


def cmd_monitor() -> dict:
    """Daily monitoring — check bot health and trading state."""
    status = cmd_status()
    report = cmd_report()

    state = get_trading_state()
    pm2 = status["pm2"]

    # Build monitor summary
    summary = {
        "bot_alive": pm2.get("running", False),
        "pid": pm2.get("pid"),
        "uptime_seconds": None,
        "balance": state.get("balance"),
        "total_trades": state.get("total_trades"),
        "wins": state.get("wins"),
        "losses": state.get("losses"),
        "winrate": None,
        "open_positions": None,
        "polymarket_markets_available": status.get("polymarket_markets", {}).get("available", False),
        "polymarket_market_count": status.get("polymarket_markets", {}).get("count", 0),
    }

    if state.get("total_trades", 0) > 0:
        w = state.get("wins", 0)
        l = state.get("losses", 0)
        total = w + l
        summary["winrate"] = round(w / total * 100, 1) if total > 0 else None

    # Count open positions from fill_log
    if FILL_LOG.exists():
        try:
            with open(FILL_LOG) as f:
                fills = json.load(f)
            open_pos = [f for f in fills if f.get("filled") and not f.get("resolved")]
            summary["open_positions"] = len(open_pos)
        except (json.JSONDecodeError, IOError):
            pass

    return summary


def format_status_text(status: dict) -> str:
    """Format status dict as readable text for Telegram."""
    pm2 = status.get("pm2", {})
    state = status.get("trading", {})
    bot = status.get("bot", {})
    polymkt = status.get("polymarket_markets", {})

    lines = [
        "=== ALTER BOT V2 STATUS ===",
        f"PM2:       {'ONLINE' if pm2.get('running') else 'OFFLINE'} | PID: {pm2.get('pid', 'N/A')}",
        f"Balance:   ${state.get('balance', 'N/A')}",
        f"Trades:    {state.get('total_trades', 0)} total | W: {state.get('wins', 0)} | L: {state.get('losses', 0)}",
        f"Win Rate:  {round(state.get('wins', 0) / max(state.get('wins', 0) + state.get('losses', 0), 1) * 100, 1)}%",
        f"PM2 Mem:  {pm2.get('memory', 'N/A')} | CPU: {pm2.get('cpu', 'N/A')}%",
        f"PM2 Restarts: {pm2.get('restarts', 0)}",
        f"Temp Markets: {'AVAILABLE' if polymkt.get('available') else 'NONE (' + str(polymkt.get('count', 0)) + ' open)'}",
    ]

    return "\n".join(lines)


def main():
    if len(sys.argv) < 2:
        print("Usage: runner.py <status|start|stop|restart|monitor|report|logs>")
        sys.exit(1)

    cmd = sys.argv[1].lower()

    if cmd == "status":
        result = cmd_status()
        print(json.dumps(result, indent=2))
    elif cmd == "start":
        result = cmd_start()
        print(json.dumps(result, indent=2))
    elif cmd == "stop":
        result = cmd_stop()
        print(json.dumps(result, indent=2))
    elif cmd == "restart":
        result = cmd_restart()
        print(json.dumps(result, indent=2))
    elif cmd == "monitor":
        result = cmd_monitor()
        print(json.dumps(result, indent=2))
    elif cmd == "report":
        result = cmd_report()
        print(json.dumps(result, indent=2, ensure_ascii=False))
    elif cmd == "logs":
        lines = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        result = cmd_logs(lines)
        print(json.dumps(result, indent=2))
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()
