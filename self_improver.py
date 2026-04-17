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
    
    def add_error(self, city, forecast_c, actual_c):
        """Add a new error observation."""
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
        
        # Add sample
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
        
        # Recalculate stats
        samples = self.errors["cities"][city]["samples"]
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
        
        self.save()
    
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