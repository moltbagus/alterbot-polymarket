#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Resolution Source Mapping - Alter-Bot-V2 Self-Improvement System
================================================================
Maps cities to their resolution data sources with unit specifications.
Tracks which weather services provide resolution data for each city.

Sources:
- HKO: Hong Kong Observatory (VHHH)
- WSSS: Singapore Changi (Wunderground)
- RJTT: Tokyo Haneda (Wunderground)
- KLGA: NYC LaGuardia (Fahrenheit)
- KORD: Chicago O'Hare (Fahrenheit)
"""

from typing import Dict, Optional, Tuple

# =============================================================================
# CITY/RESOLUTION SOURCE MAPPING
# =============================================================================

# Maps city slug to (ICAO station, unit, resolution source, source name)
RESOLUTION_SOURCES: Dict[str, Dict] = {
    # Asia - Celsius cities with specific resolution sources
    "hong-kong": {
        "station": "VHHH",
        "unit": "C",
        "source": "HKO",
        "source_name": "Hong Kong Observatory",
        "api_url": "https://www.hko.gov.hk/tc/cLIMWWW/obs/monthlydata/index.html",
    },
    "singapore": {
        "station": "WSSS",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/sg/singapore/WSSS",
    },
    "tokyo": {
        "station": "RJTT",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/jp/tokyo/RJTT",
    },
    "taipei": {
        "station": "RCSS",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/tw/taipei/RCSS",
    },
    "seoul": {
        "station": "RKSL",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/kr/seoul/RKSL",
    },
    "osaka": {
        "station": "RJOO",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/jp/osaka/RJOO",
    },
    "bangkok": {
        "station": "VTBD",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/th/bangkok/VTBD",
    },
    "shanghai": {
        "station": "ZSSS",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/cn/shanghai/ZSSS",
    },
    # US - Fahrenheit cities
    "nyc": {
        "station": "KLGA",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "chicago": {
        "station": "KORD",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "miami": {
        "station": "KMIA",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "dallas": {
        "station": "KDFW",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "la": {
        "station": "KLAX",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "seattle": {
        "station": "KSEA",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "boston": {
        "station": "KBOS",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "denver": {
        "station": "KDEN",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    "atlanta": {
        "station": "KATL",
        "unit": "F",
        "source": "METAR",
        "source_name": "FAA METAR (ADDS)",
        "api_url": "https://aviationweather.gov/api/data/metar",
    },
    # Europe - Celsius cities
    "london": {
        "station": "EGLL",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/gb/london/EGLL",
    },
    "paris": {
        "station": "LFPG",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/fr/paris/LFPG",
    },
    "munich": {
        "station": "EDDM",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/de/munich/EDDM",
    },
    "amsterdam": {
        "station": "EHAM",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/nl/amsterdam/EHAM",
    },
    "madrid": {
        "station": "LEMD",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/es/madrid/LEMD",
    },
    "rome": {
        "station": "LIRF",
        "unit": "C",
        "source": "WUNDERGROUND",
        "source_name": "Weather Underground",
        "api_url": "https://www.wunderground.com/history/daily/it/rome/LIRF",
    },
}


def get_resolution_source(city_slug: str) -> Optional[Dict]:
    """Get resolution source info for a city."""
    return RESOLUTION_SOURCES.get(city_slug.lower())


def get_city_unit(city_slug: str) -> str:
    """Get the temperature unit (C or F) for a city."""
    info = get_resolution_source(city_slug)
    return info["unit"] if info else "C"


def get_station_code(city_slug: str) -> Optional[str]:
    """Get the ICAO station code for a city."""
    info = get_resolution_source(city_slug)
    return info["station"] if info else None


def is_fahrenheit_city(city_slug: str) -> bool:
    """Check if a city uses Fahrenheit."""
    return get_city_unit(city_slug) == "F"


# =============================================================================
# UNIT CONVERSION UTILITIES
# =============================================================================

def celsius_to_fahrenheit(celsius: float) -> float:
    """
    Convert Celsius to Fahrenheit with precision.
    Formula: F = C × 1.8 + 32
    """
    return celsius * 1.8 + 32.0


def fahrenheit_to_celsius(fahrenheit: float) -> float:
    """
    Convert Fahrenheit to Celsius with precision.
    Formula: C = (F - 32) / 1.8
    """
    return (fahrenheit - 32.0) / 1.8


def convert_temperature(temp: float, from_unit: str, to_unit: str) -> float:
    """
    Convert temperature between Celsius and Fahrenheit.
    
    Args:
        temp: Temperature value
        from_unit: Source unit ("C" or "F")
        to_unit: Target unit ("C" or "F")
    
    Returns:
        Converted temperature
    """
    if from_unit == to_unit:
        return temp
    elif from_unit == "C" and to_unit == "F":
        return celsius_to_fahrenheit(temp)
    elif from_unit == "F" and to_unit == "C":
        return fahrenheit_to_celsius(temp)
    else:
        raise ValueError(f"Invalid units: {from_unit} to {to_unit}")


def normalize_to_celsius(temp: float, unit: str) -> float:
    """Normalize temperature to Celsius."""
    return convert_temperature(temp, unit, "C")


def normalize_to_fahrenheit(temp: float, unit: str) -> float:
    """Normalize temperature to Fahrenheit."""
    return convert_temperature(temp, unit, "F")


# =============================================================================
# SOURCE-SPECIFIC RESOLUTION LOGIC
# =============================================================================

def resolve_hko_temperature(date: str, station: str = "VHHH") -> Optional[float]:
    """
    Get actual temperature from Hong Kong Observatory.
    Uses HKO's daily data for resolution.
    
    Args:
        date: Date in YYYY-MM-DD format
        station: ICAO station code (default: VHHH)
    
    Returns:
        Temperature in Celsius or None if unavailable
    """
    import requests
    from bs4 import BeautifulSoup
    
    try:
        # HKO monthly data format
        year, month, day = date.split("-")
        url = f"https://www.hko.gov.hk/tc/cLIMWWW/obs/monthlydata/{year}{month}e.html"
        
        # Note: This is a placeholder - actual implementation would scrape HKO
        # For now, return None to use fallback methods
        return None
    except Exception as e:
        print(f"  [HKO] Error fetching: {e}")
        return None


def resolve_wunderground_temperature(date: str, station: str) -> Optional[float]:
    """
    Get actual temperature from Weather Underground historical data.
    
    Args:
        date: Date in YYYY-MM-DD format
        station: ICAO station code (e.g., WSSS, RJTT)
    
    Returns:
        Temperature in Celsius or None if unavailable
    """
    import requests
    from bs4 import BeautifulSoup
    
    try:
        year, month, day = date.split("-")
        
        # Wunderground historical format
        # URL pattern: /history/daily/{country}/{city}/{station}/date/{year}/{month}/{day}
        station_info = RESOLUTION_SOURCES.get(station.lower(), {})
        country = station_info.get("country", "unknown")
        city_name = station_info.get("city", "unknown")
        
        url = f"https://www.wunderground.com/history/daily/{country}/{city_name}/{station}/date/{year}/{month}/{day}"
        
        # Placeholder - actual implementation would parse the page
        return None
    except Exception as e:
        print(f"  [Wunderground] Error fetching: {e}")
        return None


def resolve_metar_temperature(date: str, station: str) -> Optional[float]:
    """
    Get actual temperature from FAA METAR data via ADDS API.
    
    Args:
        date: Date in YYYY-MM-DD format
        station: ICAO station code (e.g., KLGA, KORD)
    
    Returns:
        Temperature in Fahrenheit or None if unavailable
    """
    import requests
    
    try:
        year, month, day = date.split("-")
        
        # ADDS API for historical METAR
        url = f"https://aviationweather.gov/api/data/metar"
        params = {
            "stationIds": station,
            "year": year,
            "month": month,
            "day": day,
        }
        
        response = requests.get(url, params=params, timeout=10)
        if response.status_code == 200:
            data = response.json()
            if data and len(data) > 0:
                # Extract temperature (convert from Celsius to Fahrenheit if needed)
                temp_c = data[0].get("temp")
                if temp_c is not None:
                    return celsius_to_fahrenheit(temp_c)  # METAR returns Celsius
        
        return None
    except Exception as e:
        print(f"  [METAR] Error fetching: {e}")
        return None


def get_resolution_temperature(city_slug: str, date: str) -> Optional[Tuple[float, str]]:
    """
    Get actual temperature for a resolved market.
    
    Args:
        city_slug: City identifier
        date: Date in YYYY-MM-DD format
    
    Returns:
        Tuple of (temperature, unit) or None
    """
    info = get_resolution_source(city_slug)
    if not info:
        return None
    
    station = info["station"]
    source = info["source"]
    
    temp = None
    
    if source == "HKO":
        temp = resolve_hko_temperature(date, station)
        if temp:
            return temp, "C"
    
    elif source == "WUNDERGROUND":
        temp = resolve_wunderground_temperature(date, station)
        if temp:
            return temp, "C"
    
    elif source == "METAR":
        temp = resolve_metar_temperature(date, station)
        if temp:
            return temp, "F"
    
    return None


# =============================================================================
# BACKTEST DATA MANAGEMENT
# =============================================================================

import json
from pathlib import Path
from datetime import datetime, timedelta

BACKTEST_DIR = Path(__file__).parent / "data" / "backtest"


def ensure_backtest_dir():
    """Ensure backtest directory exists."""
    BACKTEST_DIR.mkdir(parents=True, exist_ok=True)


def save_backtest_data(city: str, date: str, forecast: float, actual: float, unit: str):
    """
    Save a backtest data point.
    
    Args:
        city: City slug
        date: Date in YYYY-MM-DD format
        forecast: Forecasted temperature
        actual: Actual temperature
        unit: Temperature unit (C or F)
    """
    ensure_backtest_dir()
    
    file_path = BACKTEST_DIR / f"{city}.json"
    
    # Load existing data
    if file_path.exists():
        with open(file_path, "r") as f:
            data = json.load(f)
    else:
        data = {"city": city, "records": []}
    
    # Add new record
    data["records"].append({
        "date": date,
        "forecast": round(forecast, 2),
        "actual": round(actual, 2),
        "error": round(forecast - actual, 2),
        "unit": unit,
        "timestamp": datetime.now().isoformat(),
    })
    
    # Sort by date
    data["records"].sort(key=lambda x: x["date"])
    
    # Save
    with open(file_path, "w") as f:
        json.dump(data, f, indent=2)


def load_backtest_data(city: str, months: int = 24) -> list:
    """
    Load backtest data for a city.
    
    Args:
        city: City slug
        months: Number of months to load (default: 24)
    
    Returns:
        List of backtest records
    """
    file_path = BACKTEST_DIR / f"{city}.json"
    
    if not file_path.exists():
        return []
    
    with open(file_path, "r") as f:
        data = json.load(f)
    
    # Filter to last N months
    cutoff = (datetime.now() - timedelta(days=months * 30)).strftime("%Y-%m-%d")
    records = [r for r in data.get("records", []) if r["date"] >= cutoff]
    
    return records


def calculate_backtest_metrics(city: str, months: int = 24) -> Dict:
    """
    Calculate backtest metrics for a city.
    
    Args:
        city: City slug
        months: Number of months to analyze
    
    Returns:
        Dictionary of metrics (MAE, RMSE, bias, sample_size)
    """
    records = load_backtest_data(city, months)
    
    if not records:
        return {
            "city": city,
            "months": months,
            "sample_size": 0,
            "mae": None,
            "rmse": None,
            "bias": None,
            "accuracy_rate": None,
        }
    
    errors = [r["error"] for r in records]
    abs_errors = [abs(e) for e in errors]
    
    mae = sum(abs_errors) / len(abs_errors)
    rmse = (sum(e**2 for e in errors) / len(errors)) ** 0.5
    bias = sum(errors) / len(errors)
    
    # Accuracy within 1 degree
    accurate = sum(1 for e in abs_errors if e <= 1.0)
    accuracy_rate = accurate / len(errors)
    
    return {
        "city": city,
        "months": months,
        "sample_size": len(records),
        "mae": round(mae, 2),
        "rmse": round(rmse, 2),
        "bias": round(bias, 2),
        "accuracy_rate": round(accuracy_rate, 2),
    }


# =============================================================================
# POLYMARKET HISTORICAL DATA (24-month backtest)
# =============================================================================

def fetch_polymarket_historical(city: str, months: int = 24) -> list:
    """
    Fetch historical market data from Polymarket API.
    This enables 24-month backtesting capability.
    
    Args:
        city: City slug
        months: Number of months to fetch
    
    Returns:
        List of historical market events
    """
    import requests
    
    # Polymarket GraphQL API for historical markets
    query = """
    query GetHistoricalMarkets($condition: EventCondition!) {
        markets(condition: $condition, limit: 100) {
            id
            question
            description
            startDate
            endDate
            resolution
            volume
            liquidity
            outcomes {
                id
                title
                probability
            }
        }
    }
    """
    
    # Map city to Polymarket market query terms
    city_search = city.replace("-", " ")
    
    # This is a placeholder - actual implementation would use Polymarket's API
    # For now, return empty list as API requires authentication
    return []


# =============================================================================
# SELF-IMPROVEMENT LEARNING
# =============================================================================

def learn_from_resolution(city_slug: str, forecast: float, actual: float, unit: str):
    """
    Learn from a resolved prediction to improve future accuracy.
    
    Args:
        city_slug: City identifier
        forecast: Forecasted temperature
        actual: Actual temperature (resolved)
        unit: Temperature unit
    """
    from datetime import datetime
    
    # Save for backtest analysis
    date_str = datetime.now().strftime("%Y-%m-%d")
    save_backtest_data(city_slug, date_str, forecast, actual, unit)
    
    # Calculate and report metrics
    metrics = calculate_backtest_metrics(city_slug, months=24)
    
    if metrics["sample_size"] > 0:
        print(f"  [LEARNED] {city_slug}: {metrics['sample_size']} samples, "
              f"MAE: {metrics['mae']}°, Bias: {metrics['bias']}°")


# =============================================================================
# MAIN - Test the module
# =============================================================================

if __name__ == "__main__":
    print("=== Resolution Source Mapping ===")
    for city in ["hong-kong", "singapore", "tokyo", "nyc", "chicago"]:
        info = get_resolution_source(city)
        if info:
            print(f"  {city}: {info['station']} ({info['unit']}) - {info['source_name']}")
    
    print("\n=== Unit Conversion Test ===")
    print(f"  25°C -> F: {celsius_to_fahrenheit(25.0):.1f}°F")
    print(f"  77°F -> C: {fahrenheit_to_celsius(77.0):.1f}°C")
    
    print("\n=== Backtest Metrics ===")
    for city in ["hong-kong", "tokyo", "singapore"]:
        metrics = calculate_backtest_metrics(city, months=24)
        print(f"  {city}: {metrics}")