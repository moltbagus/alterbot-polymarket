#!/usr/bin/env python3
"""
Run optimization tasks:
1. Check resolved markets
2. Update city accuracy (sigma)
3. Print updated calibration
"""
import json
from pathlib import Path

DATA_DIR = Path("data")
CALIBRATION_FILE = DATA_DIR / "calibration.json"

# Load existing accuracy data
CITY_ACCURACY = {
    "singapore": 0.4, "shanghai": 0.8, "seoul": 0.9,
    "paris": 1.2, "london": 1.8, "tokyo": 1.2,
    "nyc": 1.5, "chicago": 1.5, "hong-kong": 1.0,
    "miami": 1.5, "dallas": 2.0, "seattle": 2.0,
    "atlanta": 2.0, "munich": 4.0, "ankara": 3.5,
    "lucknow": 3.0, "tel-aviv": 3.0, "toronto": 2.5,
    "sao-paulo": 5.0, "buenos-aires": 7.0, "wellington": 2.5,
}

def load_cal():
    if CALIBRATION_FILE.exists():
        return json.loads(CALIBRATION_FILE.read_text())
    return {}

def check_resolutions():
    """Check which markets are resolved."""
    import requests
    markets_dir = DATA_DIR / "markets"
    resolved = 0
    
    for mkt_file in markets_dir.glob("*.json"):
        try:
            with open(mkt_file) as f:
                mkt = json.load(f)
            
            if mkt.get("status") == "open":
                city = mkt.get("city", "")
                date = mkt.get("date", "")
                event_slug = f"highest-temperature-in-{city}-on-{date}"
                
                url = f"https://gamma-api.polymarket.com/markets?eventSlug={event_slug}"
                data = requests.get(url, timeout=5).json()
                
                if data and len(data) > 0:
                    m = data[0]
                    if m.get("closed") and m.get("resolved"):
                        for t in m.get("tokens", []):
                            if t.get("winner"):
                                temp = float(t.get("outcome", "0").replace("°C", "").replace("°F", ""))
                                mkt["actual_temp"] = temp
                                mkt["resolved_outcome"] = t.get("outcome")
                                mkt["status"] = "resolved"
                                with open(mkt_file, "w") as f:
                                    json.dump(mkt, f, indent=2)
                                resolved += 1
                                print(f"✅ Resolved: {city} {date} = {temp}°C")
        except Exception as e:
            pass
    
    print(f"\nTotal newly resolved: {resolved}")
    return resolved

def update_sigma():
    """Update sigma based on resolved outcomes."""
    cal = load_cal()
    markets_dir = DATA_DIR / "markets"
    updates = []
    
    for mkt_file in markets_dir.glob("*.json"):
        try:
            with open(mkt_file) as f:
                mkt = json.load(f)
            
            if mkt.get("status") != "resolved" or not mkt.get("actual_temp"):
                continue
            
            city = mkt.get("city")
            if not city:
                continue
            
            # Get forecast
            snaps = mkt.get("forecast_snapshots", [])
            if not snaps:
                continue
            forecast = snaps[-1].get("best") or snaps[-1].get("ecmwf")
            if not forecast:
                continue
            
            actual = mkt.get("actual_temp")
            error = abs(forecast - actual)
            
            key = f"{city}_ecmwf"
            old_sigma = cal.get(key, {}).get("sigma", CITY_ACCURACY.get(city, 2.5))
            n = cal.get(key, {}).get("n", 0)
            
            alpha = 0.3
            new_sigma = round(alpha * error + (1 - alpha) * old_sigma, 2)
            
            cal[key] = {"sigma": new_sigma, "n": n+1, "last_error": round(error, 2)}
            updates.append((city, old_sigma, new_sigma, error))
        except:
            pass
    
    CALIBRATION_FILE.write_text(json.dumps(cal, indent=2))
    
    if updates:
        print("\n📊 SIGMA UPDATES:")
        for city, old, new, err in updates:
            print(f"  {city}: {old}°C → {new}°C (error: {err:.1f}°C)")
    
    return len(updates)

if __name__ == "__main__":
    print("=" * 50)
    print("RUNNING OPTIMIZATIONS")
    print("=" * 50)
    
    print("\n1. Checking resolved markets...")
    check_resolutions()
    
    print("\n2. Updating city accuracy (sigma)...")
    update_sigma()
    
    print("\n3. Current calibration:")
    cal = load_cal()
    if cal:
        for k, v in sorted(cal.items()):
            print(f"  {k}: sigma={v.get('sigma')}°C, n={v.get('n',0)}")
    else:
        print("  No calibration data yet (need resolved markets)")
    
    print("\n✅ Optimizations complete!")
