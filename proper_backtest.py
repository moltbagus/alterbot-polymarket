#!/usr/bin/env python3
"""
PROPER BACKTEST for ALTER BOT - Using Open-Meteo Archive API
===========================================================
Compares our forecast_temperature to ACTUAL resolved temperature from Open-Meteo.

Methodology:
- Load all trades from markets/*.json
- For each trade, get our forecast_temp
- Fetch actual daily max temp from Open-Meteo archive for that date/location
- Compare: Did we predict within 1°C of actual?
- Calculate true win rate
"""

import json
import os
import glob
import asyncio
import aiohttp
import re
from datetime import datetime
from collections import defaultdict

DATA_DIR = os.path.expanduser("~/.openclaw/workspace/alter-bot-v1/data")
MARKETS_DIR = os.path.join(DATA_DIR, "markets")
OUTPUT_FILE = os.path.join(DATA_DIR, "proper_backtest_results.json")

# City to lat/lon mapping
CITY_COORDS = {
    "tokyo": {"lat": 35.68, "lon": 139.69},
    "singapore": {"lat": 1.35, "lon": 103.98},
    "taipei": {"lat": 25.03, "lon": 121.56},
    "seoul": {"lat": 37.57, "lon": 126.98},
    "hong kong": {"lat": 22.32, "lon": 114.17},
    "shanghai": {"lat": 31.23, "lon": 121.47},
    "beijing": {"lat": 39.90, "lon": 116.41},
    "london": {"lat": 51.51, "lon": -0.13},
    "paris": {"lat": 48.86, "lon": 2.35},
    "nyc": {"lat": 40.78, "lon": -73.97},
    "new york city": {"lat": 40.78, "lon": -73.97},
    "chicago": {"lat": 41.88, "lon": -87.63},
    "mumbai": {"lat": 19.08, "lon": 72.88},
    "delhi": {"lat": 28.61, "lon": 77.21},
    "atlanta": {"lat": 33.75, "lon": -84.39},
    "dallas": {"lat": 32.78, "lon": -96.80},
    "denver": {"lat": 39.74, "lon": -104.99},
    "houston": {"lat": 29.76, "lon": -95.37},
    "madrid": {"lat": 40.42, "lon": -3.70},
    "miami": {"lat": 25.76, "lon": -80.19},
    "munich": {"lat": 48.14, "lon": 11.58},
    "sao-paulo": {"lat": -23.55, "lon": -46.63},
    "seattle": {"lat": 47.61, "lon": -122.33},
    "tel-aviv": {"lat": 32.08, "lon": 34.79},
    "toronto": {"lat": 43.65, "lon": -79.38},
    "wellington": {"lat": -41.29, "lon": 174.78},
    "ankara": {"lat": 39.93, "lon": 32.85},
    "buenos-aires": {"lat": -34.60, "lon": -58.38},
    "lucknow": {"lat": 26.85, "lon": 80.95},
    "houston": {"lat": 29.76, "lon": -95.37},
    "shanghai": {"lat": 31.23, "lon": 121.47},
}

# Cache file for actual temps
CACHE_FILE = os.path.join(DATA_DIR, "openmeteo_actual_cache.json")

def load_cache():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as f:
            return json.load(f)
    return {}

def save_cache(cache):
    with open(CACHE_FILE, "w") as f:
        json.dump(cache, f, indent=2)

async def fetch_actual_temps(session, city_dates, cache):
    """
    Fetch actual temperatures from Open-Meteo Archive API.
    city_dates: dict of {city: [dates]}
    Returns: cache dict with "city:date" -> temp
    """
    return cache

async def fetch_actual_temp_for_city_date(session, city, date_str):
    """Fetch actual temp for a single city/date from Open-Meteo."""
    cache_key = f"{city}:{date_str}"
    
    coords = CITY_COORDS.get(city.lower())
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
            if temps and len(temps) > 0 and temps[0] is not None:
                return temps[0]
            return None
    except Exception as e:
        print(f"Error fetching {city} {date_str}: {e}")
        return None

def fahrenheit_to_celsius(f):
    """Convert Fahrenheit to Celsius."""
    return (f - 32) * 5 / 9

def is_fahrenheit(val):
    """Check if a value is likely in Fahrenheit (values > 40 are almost certainly F)."""
    return val > 40

def normalize_temp(val):
    """Normalize temperature to Celsius - convert F to C if needed."""
    if is_fahrenheit(val):
        return fahrenheit_to_celsius(val)
    return val

def load_trades():
    """Load all trades from JSON files."""
    trades = []
    files = glob.glob(os.path.join(MARKETS_DIR, "*.json"))
    
    for filepath in files:
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            filename = os.path.basename(filepath)
            match = re.match(r"^(.+)_(\d{4}-\d{2}-\d{2})\.json$", filename)
            if not match:
                continue
            
            city = match.group(1)
            date_str = match.group(2)
            
            position = data.get("position")
            if not position:
                continue
            
            forecast_temp = position.get("forecast_temp")
            if forecast_temp is None:
                continue
            
            trades.append({
                "city": city,
                "date": date_str,
                "forecast_temp": forecast_temp,
                "forecast_src": position.get("forecast_src", "unknown"),
                "bucket_low": position.get("bucket_low"),
                "bucket_high": position.get("bucket_high"),
                "p": position.get("p", 0),
                "pnl": position.get("pnl"),
            })
        except Exception as e:
            print(f"Error loading {filepath}: {e}")
    
    return trades

async def run_backtest():
    print("=" * 60)
    print("ALTER BOT - PROPER BACKTEST (Open-Meteo)")
    print("=" * 60)
    
    # Load trades
    trades = load_trades()
    print(f"Loaded {len(trades)} trades")
    
    # Get unique city-date pairs
    city_dates = defaultdict(set)
    for t in trades:
        city_dates[t["city"]].add(t["date"])
    
    print(f"Unique cities: {len(city_dates)}")
    
    # Load cache
    cache = load_cache()
    print(f"Cached temps: {len(cache)}")
    
    # Fetch missing temps
    async with aiohttp.ClientSession() as session:
        total = sum(len(dates) for dates in city_dates.values())
        done = 0
        
        for city, dates in city_dates.items():
            for date_str in sorted(dates):
                cache_key = f"{city}:{date_str}"
                if cache_key in cache:
                    continue
                
                done += 1
                print(f"[{done}/{total}] Fetching {city} {date_str}...", end=" ")
                
                temp = await fetch_actual_temp_for_city_date(session, city, date_str)
                if temp is not None:
                    cache[cache_key] = temp
                    print(f"{temp}°C")
                else:
                    print("not found")
                
                # Rate limit
                await asyncio.sleep(0.3)
                
                # Save periodically
                if done % 20 == 0:
                    save_cache(cache)
        
        save_cache(cache)
    
    # Calculate results
    wins = 0
    losses = 0
    no_actual = 0
    city_stats = defaultdict(lambda: {"wins": 0, "losses": 0, "no_actual": 0})
    results = []
    
    for t in trades:
        city = t["city"]
        date_str = t["date"]
        forecast = t["forecast_temp"]
        cache_key = f"{city}:{date_str}"
        actual = cache.get(cache_key)
        
        if actual is None:
            no_actual += 1
            city_stats[city]["no_actual"] += 1
            results.append({
                "city": city,
                "date": date_str,
                "forecast": forecast,
                "actual": None,
                "win": None
            })
            continue
        
        # Normalize forecast to Celsius (convert from F if needed)
        forecast_c = normalize_temp(forecast)
        diff = abs(forecast_c - actual)
        is_win = diff <= 1.0
        
        if is_win:
            wins += 1
            city_stats[city]["wins"] += 1
        else:
            losses += 1
            city_stats[city]["losses"] += 1
        
        results.append({
            "city": city,
            "date": date_str,
            "forecast": forecast,
            "actual": actual,
            "diff": round(diff, 2),
            "win": is_win
        })
    
    total_resolved = wins + losses
    win_rate = (wins / total_resolved * 100) if total_resolved > 0 else 0
    
    # Build output
    output = {
        "description": "Proper backtest using Open-Meteo actual temps",
        "generated_at": datetime.now().isoformat(),
        "total_predictions": len(trades),
        "total_resolved": total_resolved,
        "no_actual": no_actual,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "win_within_1c": True,
        "city_breakdown": {},
        "sample_results": results[:50]
    }
    
    for city, stats in city_stats.items():
        total = stats["wins"] + stats["losses"]
        wr = (stats["wins"] / total * 100) if total > 0 else 0
        output["city_breakdown"][city] = {
            "wins": stats["wins"],
            "losses": stats["losses"],
            "no_actual": stats["no_actual"],
            "total": total,
            "win_rate_pct": round(wr, 2)
        }
    
    # Save
    with open(OUTPUT_FILE, "w") as f:
        json.dump(output, f, indent=2)
    
    print("\n" + "=" * 60)
    print("RESULTS")
    print("=" * 60)
    print(f"Total predictions: {len(trades)}")
    print(f"Resolved: {total_resolved}")
    print(f"No actual: {no_actual}")
    print(f"Wins: {wins}")
    print(f"Losses: {losses}")
    print(f"WIN RATE: {win_rate:.1f}%")
    print(f"\nResults saved to: {OUTPUT_FILE}")
    
    # Per-city
    print("\nPer-city breakdown:")
    for city, stats in sorted(city_stats.items(), key=lambda x: x[1]["wins"]/(x[1]["wins"]+x[1]["losses"]+0.001), reverse=True):
        total = stats["wins"] + stats["losses"]
        if total > 0:
            wr = stats["wins"] / total * 100
            print(f"  {city}: {stats['wins']}/{total} ({wr:.0f}%)")
    
    return output

if __name__ == "__main__":
    asyncio.run(run_backtest())