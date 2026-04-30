#!/usr/bin/env python3
"""
SELF-IMPROVEMENT SYSTEM - Alter Bot v1
======================================
Tracks forecast errors and updates city parameters dynamically.
Tracks: sigma, bias, min_confidence per city.
"""

import json
import os
import re
from pathlib import Path
from datetime import datetime
from collections import defaultdict
import asyncio
import aiohttp

DATA_DIR = Path(__file__).parent / "data"
CITY_ERRORS_FILE = DATA_DIR / "city_error_history.json"
CONFIG_FILE = Path(__file__).parent / "config.json"

# Self-Improver observation path
_OBSERVATION_DIR = Path.home() / ".openclaw" / "workspace" / "memory" / "self-improvement" / "observations"

# Portfolio alert file — written when balance drops >30% from peak
_PORTFOLIO_ALERT_FILE = DATA_DIR / "portfolio_alerts.json"


def check_portfolio_health(current_balance: float, peak_balance: float, min_drawdown_pct: float = 0.30) -> dict:
    """Check portfolio health and emit alert if drawdown exceeds threshold.

    FIX 4: Portfolio collapse was invisible to self-improvement system.
    Now emits an alert file when balance drops >min_drawdown_pct from peak.

    Returns dict with alert info if triggered, None otherwise.
    """
    if peak_balance <= 0:
        return None
    drawdown = (peak_balance - current_balance) / peak_balance
    if drawdown < min_drawdown_pct:
        return None

    alert = {
        "timestamp": datetime.now().isoformat(),
        "current_balance": round(current_balance, 2),
        "peak_balance": round(peak_balance, 2),
        "drawdown_pct": round(drawdown * 100, 1),
        "drawdown_amount": round(peak_balance - current_balance, 2),
    }

    # Append to alert file
    alerts = []
    if _PORTFOLIO_ALERT_FILE.exists():
        try:
            with open(_PORTFOLIO_ALERT_FILE) as f:
                alerts = json.load(f)
        except Exception:
            alerts = []

    # Avoid duplicate alerts for same drawdown level
    if alerts and alerts[-1].get("drawdown_pct") == alert["drawdown_pct"]:
        return alert  # already alerted at this level

    alerts.append(alert)
    try:
        with open(_PORTFOLIO_ALERT_FILE, "w") as f:
            json.dump(alerts[-20:], f, indent=2)  # keep last 20 alerts
    except Exception as e:
        print(f"[self_improver] Failed to write portfolio alert: {e}")

    print(f"\n🚨 [PORTFOLIO ALERT] Drawdown {alert['drawdown_pct']:.1f}% "
          f"(${alert['drawdown_amount']:.2f} lost) | "
          f"Peak: ${alert['peak_balance']:.2f} → Now: ${alert['current_balance']:.2f}\n")
    return alert

# ============================================================================
# ERROR TRACKING
# ============================================================================

# ============================================================================
# RESOLUTION SOURCE MAPPING
# Maps each city to its Polymarket resolution station.
# Used for calibration filtering (only use forecasts from matching source).
# ============================================================================

CITY_COORDS = {
    # HONG KONG: Polymarket resolves on HKO Observatory downtown, NOT VHHH airport
    "hong-kong": {"lat": 22.3025, "lon": 114.1747, "source": "HKO"},
    # Asian cities: ICAO airport stations matching Polymarket resolution
    "singapore": {"lat": 1.3502, "lon": 103.9940, "source": "WSSS"},
    "tokyo": {"lat": 35.7647, "lon": 140.3864, "source": "RJTT"},
    "seoul": {"lat": 37.4691, "lon": 126.4505, "source": "RKSI"},
    "taipei": {"lat": 25.0797, "lon": 121.2342, "source": "RCTP"},
    "shanghai": {"lat": 31.1443, "lon": 121.8083, "source": "ZSPD"},
    "ankara": {"lat": 40.1281, "lon": 32.9951, "source": "LTAC"},
    "tel-aviv": {"lat": 32.0114, "lon": 34.8867, "source": "LLBG"},
    "wellington": {"lat": -41.3272, "lon": 174.8052, "source": "NZWN"},
    # Americas
    "buenos-aires": {"lat": -34.8222, "lon": -58.5358, "source": "SAEZ"},
    "sao-paulo": {"lat": -23.4356, "lon": -46.4731, "source": "SBGR"},
    "toronto": {"lat": 43.6772, "lon": -79.6306, "source": "CYYZ"},
    # EU
    "london": {"lat": 51.5048, "lon": 0.0495, "source": "EGLC"},
    "paris": {"lat": 48.9962, "lon": 2.5979, "source": "LFPG"},
    "munich": {"lat": 48.3537, "lon": 11.7750, "source": "EDDM"},
    # US
    "nyc": {"lat": 40.7772, "lon": -73.8726, "source": "KLGA"},
    "chicago": {"lat": 41.9742, "lon": -87.9073, "source": "KORD"},
    "miami": {"lat": 25.7959, "lon": -80.2870, "source": "KMIA"},
    "dallas": {"lat": 32.8471, "lon": -96.8518, "source": "KDAL"},
    "seattle": {"lat": 47.4502, "lon": -122.3088, "source": "KSEA"},
    "atlanta": {"lat": 33.6407, "lon": -84.4277, "source": "KATL"},
}

RESOLUTION_SOURCE = {
    # HK: HKO Observatory downtown (NOT VHHH — Polymarket rules explicitly specify HKO)
    "hong-kong": "HKO",
    # All other cities: ICAO airport stations matching Polymarket/Wunderground resolution
    "singapore": "WSSS", "tokyo": "RJTT", "seoul": "RKSI",
    "taipei": "RCTP", "shanghai": "ZSPD", "ankara": "LTAC",
    "tel-aviv": "LLBG", "wellington": "NZWN",
    "buenos-aires": "SAEZ", "sao-paulo": "SBGR", "toronto": "CYYZ",
    "london": "EGLC", "paris": "LFPG", "munich": "EDDM",
    "nyc": "KLGA", "chicago": "KORD", "miami": "KMIA",
    "dallas": "KDAL", "seattle": "KSEA", "atlanta": "KATL",
}

def is_calibration_mismatch(city: str, data_source: str) -> bool:
    """Check if forecast source mismatches Polymarket resolution source.
    Only use calibration data from sources matching the resolution station.
    """
    city = city.lower()
    if city not in RESOLUTION_SOURCE:
        return False
    return data_source.upper() != RESOLUTION_SOURCE[city].upper()


class CityErrorTracker:
    """Tracks forecast errors per city for self-improvement."""
    
    def __init__(self):
        self.errors = self.load()
        self._pending_whale_skips = []  # collected whale skips for batch emit
    
    def load(self):
        """Load error history from file."""
        if CITY_ERRORS_FILE.exists():
            with open(CITY_ERRORS_FILE) as f:
                return json.load(f)
        return {"cities": {}, "last_updated": None}
    
    def save(self):
        """Save error history."""
        self.errors["last_updated"] = datetime.now().isoformat()
        with open(CITY_ERRORS_FILE, "w") as f:
            json.dump(self.errors, f, indent=2)
    
    def emit_observation(self, city, forecast, actual, bucket_min=None, bucket_max=None, market_question=None, ev_used=None, position_size=None, balance_at_scan=None, whale_skip_reason=None):
        """Emit a structured observation to the self-improver memory directory."""
        try:
            _OBSERVATION_DIR.mkdir(parents=True, exist_ok=True)
            date_str = datetime.now().strftime("%Y-%m-%d")
            obs_file = _OBSERVATION_DIR / f"{date_str}-alterbot.md"

            # Convert forecast to Celsius if Fahrenheit
            if forecast > 40:
                forecast_c = (forecast - 32) * 5/9
            else:
                forecast_c = forecast

            error_degrees = forecast_c - actual
            win = "WIN" if abs(error_degrees) <= 1.0 else "LOSS"

            entry = f"""
### Trade: {market_question or f"{city} temperature"}
- **City:** {city}
- **Bucket:** {bucket_min}-{bucket_max}°{"F" if forecast > 40 else "C"}
- **Forecast:** {forecast:.1f}°{"F" if forecast > 40 else "C"} ({forecast_c:.1f}°C)
- **Actual:** {actual:.1f}°C
- **Error:** {error_degrees:+.1f}°C
- **Outcome:** {win}
- **EV used:** {ev_used}
- **Position size:** {position_size}
- **Balance at scan:** {balance_at_scan}
- **Whale skip reason:** {whale_skip_reason or "N/A"}
- **Timestamp:** {datetime.now().strftime("%Y-%m-%d %H:%M UTC")}
"""
            # Flush pending whale skips into the observation
            if self._pending_whale_skips:
                whale_skipped = self._pending_whale_skips
                whale_reasons = [s["whale_reason"] for s in whale_skipped]
                entry += f"""
- **Whale skipped:** {len(whale_skipped)} since last emit
- **Whale reasons:** {whale_reasons}
"""
                self._pending_whale_skips = []
            with open(obs_file, "a") as f:
                f.write(entry)
        except Exception as e:
            print(f"[self_improver] Failed to emit observation: {e}")

    def add_error(self, city, forecast_c, actual_c, on_circuit_broken=None, error_type="TRADE", **kwargs):
        """Add a new error observation.

        Args:
            city: city slug
            forecast_c: forecast temperature in Celsius
            actual_c: actual temperature in Celsius
            on_circuit_broken: optional callback(city, error_count) invoked when
                circuit breaks (4+ consecutive errors or 0% win_rate at 3+ samples).
                bot_v2.py passes _persist_circuit_broken_city to persist the break.
            error_type: "TRADE" (default) or "WHALE_SKIP". WHALE_SKIP bypasses
                DATA_ERROR guard and circuit_broken checks since it's not a real trade.
        """
        city = city.lower()

        # Guard against NULL sentinel data (actual=0.0°C) — but allow WHALE_SKIP sentinels
        if error_type != "WHALE_SKIP" and actual_c <= 0.1:
            print(f"[self_improver] DATA_ERROR skip: {city} actual={actual_c:.1f}°C (likely NULL sentinel)")
            return
        if city not in self.errors["cities"]:
            self.errors["cities"][city] = {
                "samples": [],
                "avg_error": 0,
                "sigma": 2.0,
                "bias": 0,
                "win_rate": 0,
                "n_wins": 0,
                "n_total": 0
            }

        # Add sample — WHALE_SKIP uses sentinel actual=999 to distinguish from real forecasts
        if error_type == "WHALE_SKIP":
            self.errors["cities"][city]["samples"].append({
                "forecast": forecast_c,
                "actual": actual_c,
                "error": None,
                "win": None,
                "timestamp": datetime.now().isoformat(),
                "whale_skip": True,
                "whale_reason": kwargs.get("whale_skip_reason"),
            })
        else:
            err = abs(forecast_c - actual_c)
            self.errors["cities"][city]["samples"].append({
                "forecast": forecast_c,
                "actual": actual_c,
                "error": err,
                "win": err <= 1.0,
                "timestamp": datetime.now().isoformat()
            })

        # Keep last 50 samples
        if len(self.errors["cities"][city]["samples"]) > 50:
            self.errors["cities"][city]["samples"] = \
                self.errors["cities"][city]["samples"][-50:]

        # Recalculate stats — only for real trades, not WHALE_SKIP
        samples = self.errors["cities"][city]["samples"]
        if error_type == "WHALE_SKIP":
            # WHALE_SKIP doesn't affect real trade stats
            pass
        else:
            errors = [s["error"] for s in samples]
            wins = sum(1 for s in samples if s["win"])


            self.errors["cities"][city]["avg_error"] = sum(errors) / len(errors) if errors else 0
            self.errors["cities"][city]["n_wins"] = wins
            self.errors["cities"][city]["n_total"] = len(samples)
            self.errors["cities"][city]["win_rate"] = wins / len(samples) if samples else 0

            # Update sigma (approximate as 2x average error for 95% CI)
            self.errors["cities"][city]["sigma"] = self.errors["cities"][city]["avg_error"] * 2

            # Update bias (mean error direction)
            biases = [s["forecast"] - s["actual"] for s in samples]
            self.errors["cities"][city]["bias"] = sum(biases) / len(biases) if biases else 0

            # Mark circuit_broken=True when 0% win_rate on 3+ samples
            # FIX 1: invoke on_circuit_broken callback to persist to state.json,
            # config.json, city_error_history.json, and p0_alerts.json
            n_total = len(samples)
            win_rate = wins / n_total if n_total > 0 else 0
            if n_total >= 3 and win_rate == 0:
                self.errors["cities"][city]["circuit_broken"] = True
                self.errors["cities"][city]["broken_at"] = datetime.now().isoformat()
                self.errors["cities"][city]["reason"] = f"{n_total} samples, 0% win_rate"
                self.errors["cities"][city]["error_count"] = n_total
                if on_circuit_broken is not None:
                    try:
                        on_circuit_broken(city, n_total)
                    except Exception as e:
                        print(f"[self_improver] on_circuit_broken failed: {e}")

        self.save()

        # Emit observation to self-improver memory directory
        forecast_raw = kwargs.get("forecast_raw", forecast_c * 9/5 + 32 if forecast_c < 40 else forecast_c)
        self.emit_observation(
            city=city,
            forecast=kwargs.get("forecast_raw", forecast_c),
            actual=actual_c,
            bucket_min=kwargs.get("bucket_min"),
            bucket_max=kwargs.get("bucket_max"),
            market_question=kwargs.get("market_question"),
            ev_used=kwargs.get("ev_used"),
            position_size=kwargs.get("position_size"),
            balance_at_scan=kwargs.get("balance_at_scan"),
            whale_skip_reason=kwargs.get("whale_skip_reason"),
        )

    def record_whale_skip(self, city, whale_reason, forecast=None, price=None, bucket_min=None, bucket_max=None, market_question=None, ev_used=None, position_size=None, balance_at_scan=None):
        """Record a whale skip event for analysis (does not affect error stats).

        Uses sentinel actual=999 to distinguish from real forecasts.
        """
        city = city.lower()

        if city not in self.errors["cities"]:
            self.errors["cities"][city] = {
                "samples": [],
                "avg_error": 0,
                "sigma": 2.0,
                "bias": 0,
                "win_rate": 0,
                "n_wins": 0,
                "n_total": 0
            }

        # Add whale skip as a special sample (sentinel actual=999, not a real forecast)
        self.errors["cities"][city]["samples"].append({
            "forecast": forecast,
            "actual": 999,  # sentinel: no actual temp for skipped trades
            "error": None,
            "win": None,
            "timestamp": datetime.now().isoformat(),
            "whale_skip": True,
            "whale_reason": whale_reason,
        })

        # Keep last 50 samples
        if len(self.errors["cities"][city]["samples"]) > 50:
            self.errors["cities"][city]["samples"] = \
                self.errors["cities"][city]["samples"][-50:]

        self.save()

        # Append to pending whale skips so emit_observation can flush them in batch
        self._pending_whale_skips.append({
            "city": city,
            "whale_reason": whale_reason,
            "forecast": forecast,
            "price": price,
            "bucket_min": bucket_min,
            "bucket_max": bucket_max,
            "market_question": market_question,
            "ev_used": ev_used,
            "position_size": position_size,
            "balance_at_scan": balance_at_scan,
            "timestamp": datetime.now().isoformat(),
        })

    def get_sigma(self, city, default=2.0):
        """Get dynamically updated sigma."""
        city = city.lower()
        if city in self.errors["cities"]:
            return self.errors["cities"][city].get("sigma", default)
        return default
    
    def get_win_rate(self, city):
        """Get dynamic win rate for a city."""
        city = city.lower()
        if city in self.errors["cities"]:
            return self.errors["cities"][city].get("win_rate", 0.30)
        return 0.30
    
    def should_trade(self, city, min_win_rate=0.75):
        """Check if city should be traded based on recent performance."""
        win_rate = self.get_win_rate(city)
        return win_rate >= min_win_rate
    
    def get_recommended_confidence(self, city):
        """Get recommended minimum confidence for a city."""
        win_rate = self.get_win_rate(city)
        
        # Higher confidence for lower win rates
        if win_rate >= 0.90:
            return 0.50
        elif win_rate >= 0.75:
            return 0.65
        elif win_rate >= 0.60:
            return 0.80
        else:
            return 0.95


# ============================================================================
# RESOLUTION FETCHER
# ============================================================================

async def fetch_hko_temp(session, date_str: str):
    """Fetch actual temperature from Hong Kong Observatory.
    HKO publishes daily extracts matching Polymarket resolution source.
    Tries HKO official page first, falls back to Open-Meteo at HKO coords.
    """
    year = date_str[:4]
    month = int(date_str[5:7])
    day = int(date_str[8:10])
    
    hko_url = f"https://www.weather.gov.hk/en/cis/dailyExtract.htm?y={year}&m={month:02d}&d={day:02d}"
    
    try:
        async with session.get(hko_url, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 200:
                text = await resp.text()

                matches = re.findall(r'(?:Max|Highest).*?(\d+\.?\d*)\s*°C', text, re.IGNORECASE)
                if matches:
                    return float(matches[0])
    except Exception:
        pass
    
    # Fallback: Open-Meteo at HKO coordinates
    try:
        url = "https://archive-api.open-meteo.com/v1/archive"
        params = {
            "latitude": 22.3025,
            "longitude": 114.1747,
            "start_date": date_str,
            "end_date": date_str,
            "daily": "temperature_2m_max",
        }
        async with session.get(url, params=params) as resp:
            if resp.status == 200:
                data = await resp.json()
                temps = data.get("daily", {}).get("temperature_2m_max", [])
                if temps and temps[0]:
                    return float(temps[0])
    except Exception:
        pass
    
    return None


async def fetch_actual_temp(session, city, date_str):
    """Fetch actual temperature from source matching Polymarket resolution."""
    city = city.lower()
    
    # HONG KONG: Use HKO official data (matches Polymarket resolution source)
    if city == "hong-kong":
        return await fetch_hko_temp(session, date_str)
    
    coords_map = {
        "tokyo": {"lat": 35.68, "lon": 139.69},
        "singapore": {"lat": 1.35, "lon": 103.98},
        "seoul": {"lat": 37.57, "lon": 126.98},
        "london": {"lat": 51.51, "lon": -0.13},
        "paris": {"lat": 48.86, "lon": 2.35},
        "miami": {"lat": 25.76, "lon": -80.19},
        "atlanta": {"lat": 33.75, "lon": -84.39},
        "sao-paulo": {"lat": -23.55, "lon": -46.63},
    }
    
    coords = coords_map.get(city)
    if not coords:
        return None
    
    url = "https://archive-api.open-meteo.com/v1/archive"
    params = {
        "latitude": coords["lat"],
        "longitude": coords["lon"],
        "start_date": date_str,
        "end_date": date_str,
        "daily": "temperature_2m_max",
    }
    
    try:
        async with session.get(url, params=params) as resp:
            if resp.status != 200:
                return None
            data = await resp.json()
            temps = data.get("daily", {}).get("temperature_2m_max", [])
            return temps[0] if temps and temps[0] else None
    except:
        return None



async def process_resolved_markets(markets_dir):
    """Process all resolved markets and update error tracking."""
    import glob
    import re
    
    tracker = CityErrorTracker()
    processed = 0
    
    async with aiohttp.ClientSession() as session:
        for f in glob.glob(str(markets_dir / "*.json")):
            try:
                with open(f) as jf:
                    data = json.load(jf)
                
                # Check if resolved
                if data.get("status") != "closed":
                    continue
                
                if data.get("resolved_outcome") is None:
                    # Try to resolve
                    filename = os.path.basename(f)
                    match = re.match(r"^(.+)_(\d{4}-\d{2}-\d{2})\.json$", filename)
                    if not match:
                        continue
                    
                    city = match.group(1)
                    date_str = match.group(2)
                    
                    # Get actual temp (from file or fetch)
                    actual = data.get("actual_temp")
                    if actual is None:
                        actual = await fetch_actual_temp(session, city, date_str)
                    
                    if actual:
                        data["actual_temp"] = actual
                        
                        # Get forecast from forecast_snapshots (bot_v2 stores forecasts here, not position.forecast_temp)
                        forecast = None
                        snapshots = data.get("forecast_snapshots", [])
                        if snapshots:
                            # Use the last snapshot's best forecast
                            last_snap = snapshots[-1]
                            forecast = last_snap.get("best")
                        
                        # Fallback to position.forecast_temp if no snapshots
                        if forecast is None:
                            pos = data.get("position", {})
                            forecast = pos.get("forecast_temp") if pos else None
                        
                        if forecast:
                            # Convert to Celsius if Fahrenheit
                            if forecast > 40:
                                forecast_c = (forecast - 32) * 5/9
                            else:
                                forecast_c = forecast
                            
                            tracker.add_error(city, forecast_c, actual)
                            processed += 1
                            
                            # Save resolved data
                            with open(f, "w") as jf:
                                json.dump(data, jf, indent=2)
            except:
                pass
    
    print(f"Processed {processed} resolved markets")
    return tracker


# ============================================================================
# MAIN
# ============================================================================

def get_optimization_report():
    """Generate self-improvement report."""
    tracker = CityErrorTracker()
    
    report = "# Self-Improvement Report\n\n"
    
    # Sort cities by win rate
    cities = []
    for city, data in tracker.errors.get("cities", {}).items():
        if data.get("n_total", 0) >= 3:
            cities.append((city, data["win_rate"], data["avg_error"], data["sigma"], data["n_total"]))
    
    cities.sort(key=lambda x: x[1], reverse=True)
    
    report += "## City Performance (Dynamic)\n\n"
    report += "| City | Win Rate | Avg Error | Sigma | Samples |\n"
    report += "|------|---------|----------|------|--------|\n"
    
    for city, wr, err, sigma, n in cities[:15]:
        status = "✅" if wr >= 0.75 else "⚠️" if wr >= 0.50 else "❌"
        report += f"| {city} | {wr:.0%} | {err:.2f}°C | {sigma:.2f} | {n} |\n"
    
    report += f"\nLast updated: {tracker.errors.get('last_updated', 'Never')}\n"
    
    return report


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        print(get_optimization_report())
    elif len(sys.argv) > 1 and sys.argv[1] == "process":
        import asyncio
        asyncio.run(process_resolved_markets(DATA_DIR / "markets"))
    else:
        tracker = CityErrorTracker()
        print("City Error Tracker initialized")
        print(f"Tracking {len(tracker.errors.get('cities', {}))} cities")