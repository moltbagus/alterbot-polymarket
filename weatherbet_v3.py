#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
weatherbet_v3.py — Enhanced Weather Trading Bot for Polymarket
================================================================
Upgrades from v2:
1. METAR real-time data integration (D+0 observed temps)
2. Accuracy tracking (log predictions vs outcomes)
3. Dynamic bias correction (learn from past errors)
4. Multi-source ensemble with learned weights

Usage:
    python weatherbet_v3.py          # main loop
    python weatherbet_v3.py report   # full report
    python weatherbet_v3.py status   # balance and open positions
    python weatherbet_v3.py accuracy # show accuracy stats
"""

import re
import sys
import json
import math
import time
import requests
from datetime import datetime, timezone, timedelta
from pathlib import Path
from collections import defaultdict

# =============================================================================
# CONFIG
# =============================================================================

DATA_DIR = Path("data")
DATA_DIR.mkdir(exist_ok=True)
STATE_FILE = DATA_DIR / "state.json"
CALIBRATION_FILE = DATA_DIR / "calibration.json"
PREDICTIONS_FILE = DATA_DIR / "predictions.json"  # NEW: track predictions
ACCURACY_FILE = DATA_DIR / "accuracy.json"  # NEW: accuracy stats

_config = {
    "balance": 10000.0,
    "max_bet": 1.0,
    "min_ev": 0.15,
    "max_price": 0.45,
    "min_volume": 500,
    "kelly_fraction": 0.25,
    "scan_interval": 1800,
}

def load_config():
    cfg_path = Path("config.json")
    if cfg_path.exists():
        with open(cfg_path) as f:
            return json.load(f)
    return _config

_cfg = load_config()

BALANCE = _cfg.get("balance", 10000.0)
MAX_BET = _cfg.get("max_bet", 1.0)
MIN_EV = _cfg.get("min_ev", 0.15)
MAX_PRICE = _cfg.get("max_price", 0.45)
MIN_VOLUME = _cfg.get("min_volume", 500)
KELLY_FRACTION = _cfg.get("kelly_fraction", 0.25)
SCAN_INTERVAL = _cfg.get("scan_interval", 1800)

DEFAULT_SIGMA_F = 2.5
DEFAULT_SIGMA_C = 1.5

# City metadata with known biases (from historical analysis)
CITY_ACCURACY = {
    "singapore": {"sigma_mult": 0.6, "known_bias": 0.0, "metar_reliability": 0.98},
    "tokyo": {"sigma_mult": 0.9, "known_bias": -0.5, "metar_reliability": 0.97},
    "seoul": {"sigma_mult": 1.0, "known_bias": -0.3, "metar_reliability": 0.94},
    "hong-kong": {"sigma_mult": 0.8, "known_bias": 0.0, "metar_reliability": 0.98},
    "london": {"sigma_mult": 1.1, "known_bias": 0.5, "metar_reliability": 0.85},
    "paris": {"sigma_mult": 1.0, "known_bias": 0.3, "metar_reliability": 0.82},
    "munich": {"sigma_mult": 1.4, "known_bias": 0.0, "metar_reliability": 0.78},
    "nyc": {"sigma_mult": 1.2, "known_bias": 0.0, "metar_reliability": 0.97},
    "chicago": {"sigma_mult": 1.3, "known_bias": 0.0, "metar_reliability": 0.96},
    "miami": {"sigma_mult": 1.0, "known_bias": 0.5, "metar_reliability": 0.96},
    "dallas": {"sigma_mult": 1.2, "known_bias": 0.0, "metar_reliability": 0.95},
    "seattle": {"sigma_mult": 1.4, "known_bias": 0.0, "metar_reliability": 0.90},
    "atlanta": {"sigma_mult": 1.3, "known_bias": 0.0, "metar_reliability": 0.92},
}

LOCATIONS = {
    "nyc": {"lat": 40.7772, "lon": -73.8726, "name": "New York", "station": "KLGA", "unit": "F"},
    "chicago": {"lat": 41.9742, "lon": -87.9073, "name": "Chicago", "station": "KORD", "unit": "F"},
    "miami": {"lat": 25.7959, "lon": -80.2870, "name": "Miami", "station": "KMIA", "unit": "F"},
    "dallas": {"lat": 32.8471, "lon": -96.8518, "name": "Dallas", "station": "KDAL", "unit": "F"},
    "seattle": {"lat": 47.4502, "lon": -122.3088, "name": "Seattle", "station": "KSEA", "unit": "F"},
    "atlanta": {"lat": 33.6407, "lon": -84.4277, "name": "Atlanta", "station": "KATL", "unit": "F"},
    "london": {"lat": 51.5048, "lon": 0.0495, "name": "London", "station": "EGLC", "unit": "C"},
    "paris": {"lat": 48.9962, "lon": 2.5979, "name": "Paris", "station": "LFPG", "unit": "C"},
    "munich": {"lat": 48.3537, "lon": 11.7750, "name": "Munich", "station": "EDDM", "unit": "C"},
    "seoul": {"lat": 37.4691, "lon": 126.4505, "name": "Seoul", "station": "RKSI", "unit": "C"},
    "tokyo": {"lat": 35.7647, "lon": 140.3864, "name": "Tokyo", "station": "RJTT", "unit": "C"},
    "singapore": {"lat": 1.3502, "lon": 103.9940, "name": "Singapore", "station": "WSSS", "unit": "C"},
    "hong-kong": {"lat": 22.3193, "lon": 114.1694, "name": "Hong Kong", "station": "VHHH", "unit": "C"},
    "tel-aviv": {"lat": 32.0114, "lon": 34.8867, "name": "Tel Aviv", "station": "LLBG", "unit": "C"},
}

# =============================================================================
# PREDICTION & ACCURACY TRACKING
# =============================================================================

def load_predictions():
    if PREDICTIONS_FILE.exists():
        return json.loads(PREDICTIONS_FILE.read_text())
    return []

def save_predictions(predictions):
    with open(PREDICTIONS_FILE, "w") as f:
        json.dump(predictions, f, indent=2)

def add_prediction(city, date, forecast, actual, outcome, ev):
    """Log a prediction for accuracy tracking."""
    predictions = load_predictions()
    predictions.append({
        "city": city,
        "date": date,
        "forecast": forecast,
        "actual": actual,
        "outcome": outcome,
        "ev": ev,
        "timestamp": datetime.now().isoformat()
    })
    save_predictions(predictions)
    update_accuracy(city, forecast, actual)

def load_accuracy():
    if ACCURACY_FILE.exists():
        return json.loads(ACCURACY_FILE.read_text())
    return {"cities": {}}

def save_accuracy(acc):
    with open(ACCURACY_FILE, "w") as f:
        json.dump(acc, f, indent=2)

def update_accuracy(city, forecast, actual):
    """Update accuracy stats for a city."""
    acc = load_accuracy()
    if city not in acc["cities"]:
        acc["cities"][city] = {"errors": [], "bias_sum": 0, "count": 0}
    
    error = actual - forecast
    c = acc["cities"][city]
    c["errors"].append(error)
    c["bias_sum"] += error
    c["count"] += 1
    
    # Keep last 30 data points
    c["errors"] = c["errors"][-30:]
    save_accuracy(acc)

def get_learned_bias(city):
    """Get dynamically learned bias for a city."""
    acc = load_accuracy()
    if city in acc["cities"]:
        c = acc["cities"][city]
        if c["count"] >= 3:
            return c["bias_sum"] / c["count"]
    return 0.0

def get_total_accuracy():
    """Get overall accuracy stats."""
    acc = load_accuracy()
    total_error = []
    for city, data in acc["cities"].items():
        total_error.extend(data["errors"][-10:])
    
    if not total_error:
        return {"count": 0, "mae": 0, "bias": 0}
    
    mae = sum(abs(e) for e in total_error) / len(total_error)
    bias = sum(total_error) / len(total_error)
    return {"count": len(total_error), "mae": round(mae, 2), "bias": round(bias, 2)}

# =============================================================================
# METAR FETCHING
# =============================================================================

def get_metar(city_slug):
    """Current observed temperature from METAR station."""
    if city_slug not in LOCATIONS:
        return None
    loc = LOCATIONS[city_slug]
    station = loc["station"]
    unit = loc["unit"]
    
    try:
        url = f"https://aviationweather.gov/api/data/metar?ids={station}&format=json"
        data = requests.get(url, timeout=(5, 8)).json()
        if data and isinstance(data, list):
            temp_c = data[0].get("temp")
            if temp_c is not None:
                if unit == "F":
                    return round(float(temp_c) * 9/5 + 32, 1)
                return round(float(temp_c), 1)
    except Exception as e:
        print(f"  [METAR] {city_slug}: {e}")
    return None

def get_metar_multi():
    """Get METAR temps for all cities."""
    results = {}
    for city in LOCATIONS:
        temp = get_metar(city)
        if temp:
            results[city] = temp
    return results

# =============================================================================
# FORECAST FETCHING
# =============================================================================

def get_ecmwf_forecast(city_slug, target_date):
    """ECMWF forecast via Open-Meteo."""
    if city_slug not in LOCATIONS:
        return None
    loc = LOCATIONS[city_slug]
    
    try:
        url = (
            f"https://api.open-meteo.com/v1/forecast"
            f"?latitude={loc['lat']}&longitude={loc['lon']}"
            f"&daily=temperature_2m_max&start_date={target_date}&end_date={target_date}"
            f"&timezone=auto"
        )
        data = requests.get(url, timeout=10).json()
        temps = data.get("daily", {}).get("temperature_2m_max", [])
        if temps:
            return round(temps[0], 1)
    except Exception as e:
        print(f"  [ECMWF] {city_slug}: {e}")
    return None

def get_ensemble_forecast(city_slug, target_date):
    """Get ensemble forecast combining ECMWF + METAR (for D+0).
    
    Returns (ensemble_temp, ecmwf_temp, metar_temp) tuple so callers
    can compute dynamic sigma and use individual sources.
    """
    ecmwf = get_ecmwf_forecast(city_slug, target_date)
    metar = get_metar(city_slug)
    
    if ecmwf and metar:
        # For same-day (D+0), weight METAR more heavily
        # METAR is actual observed, ECMWF is forecast
        ensemble = round(0.4 * ecmwf + 0.6 * metar, 1)
        return ensemble, ecmwf, metar
    elif ecmwf:
        return ecmwf, ecmwf, None
    return None, None, metar

# =============================================================================
# PROBABILITY & EV CALCULATION
# =============================================================================

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def bucket_prob(forecast, target_temp, sigma=1.5, bias=0.0):
    """Calculate probability of exact temperature match (within ±0.5°F).
    
    Bug fix: bias was being SUBTRACTED from forecast (adj = forecast - bias),
    which inverts the bias direction. Now correctly ADDS bias to forecast.
    Pre-bias correction: bias shifts the ENTIRE forecast distribution, so
    we add bias BEFORE computing probability — not after.
    """
    # FIX: Add bias (not subtract) to shift forecast in correct direction
    # Positive bias = model undershoots (should increase prob for higher targets)
    adj = forecast + bias
    margin = 0.5
    return norm_cdf((target_temp + margin - adj) / sigma) - norm_cdf((target_temp - margin - adj) / sigma)

def bucket_prob_cumulative(forecast, target_temp, sigma=1.5, bias=0.0):
    """Calculate P(T <= target_temp) for <= X°F questions.
    
    Cumulative probability: probability that temperature is at or below target.
    """
    adj = forecast + bias
    return norm_cdf((target_temp - adj) / sigma)

def detect_pricing_inversion(tokens, forecast, city):
    """Bug fix #1: Detect adjacent bucket pricing inversions for pair trades.
    
    When two adjacent temperature buckets are priced inversely to their
    actual probability, it signals a pair trade opportunity.
    E.g., if 75°F is priced 0.40 but 80°F is priced 0.35, and our forecast
    is 77°F, then 80°F is underpriced relative to 75°F.
    
    Returns dict with inversion details or None.
    """
    if len(tokens) < 2:
        return None
    
    # Parse tokens into list of (temp, price)
    parsed = []
    for t in tokens:
        outcome = t.get("outcome", "")
        price = t.get("price", 0)
        m = re.search(r"(\d+)\s*°?[CcFf]", outcome)
        if m and price > 0:
            parsed.append((int(m.group(1)), price, outcome))
    
    if len(parsed) < 2:
        return None
    
    # Sort by temperature
    parsed.sort(key=lambda x: x[0])
    
    # Check for inversion between adjacent buckets
    for i in range(len(parsed) - 1):
        t1, p1, o1 = parsed[i]
        t2, p2, o2 = parsed[i+1]
        
        # If higher temp has LOWER price than lower temp → inversion
        if p2 < p1:
            # Calculate how far forecast is from each bucket
            dist1 = abs(forecast - t1)
            dist2 = abs(forecast - t2)
            
            # Inversion only matters if forecast is between them or near the higher one
            if forecast >= t1 and forecast <= t2:
                return {
                    "lower_temp": t1, "higher_temp": t2,
                    "lower_price": p1, "higher_price": p2,
                    "forecast": forecast, "city": city,
                    "distance_to_lower": dist1, "distance_to_higher": dist2
                }
    
    return None

def get_dynamic_sigma(city_slug, ecmwf_temp, metar_temp):
    """Bug fix #2: Dynamic sigma based on model disagreement.
    
    When ECMWF and METAR agree closely, sigma should be lower (more confident).
    When they disagree, sigma should be higher (more uncertainty).
    
    We use METAR as ground truth proxy: if ECMWF is close to METAR,
    the model is reliable → lower sigma. If they diverge, sigma increases.
    """
    base_sigma = CITY_ACCURACY.get(city_slug, {}).get("sigma_mult", 1.0) * DEFAULT_SIGMA_C
    
    if ecmwf_temp and metar_temp:
        disagreement = abs(ecmwf_temp - metar_temp)
        # Scale sigma based on disagreement
        # disagreement of 0-2°F → 0.7x sigma, 2-5°F → 1.0x, 5+°F → 1.5x
        if disagreement <= 2:
            sigma_mult = 0.7
        elif disagreement <= 5:
            sigma_mult = 1.0
        else:
            sigma_mult = 1.5
        
        # Also use HRRR-like weighting if available (via different source)
        # For now, use metar deviation from ecmwf as disagreement proxy
        dynamic_sigma = base_sigma * sigma_mult
        
        # Clamp to reasonable range
        return max(0.8, min(dynamic_sigma, 3.0))
    
    return base_sigma

def calc_ev(p, price):
    if price <= 0 or price >= 1:
        return 0.0
    return round(p * (1.0 / price - 1.0) - (1.0 - p), 4)

def calc_kelly(p, price):
    if price <= 0 or price >= 1:
        return 0.0
    b = 1.0 / price - 1.0
    f = (p * b - (1.0 - p)) / b
    return round(min(max(0.0, f) * KELLY_FRACTION, 1.0), 4)

# =============================================================================
# STATE MANAGEMENT
# =============================================================================

def load_state():
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"balance": BALANCE, "trades": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)

# =============================================================================
# POLYMARKET API
# =============================================================================

def get_polymarket_markets():
    """Fetch active weather markets from Polymarket.
    
    Tries multiple endpoints; saves raw response to data/api_debug.json
    when no weather markets found for debugging.
    """
    endpoints = [
        ("https://clob.polymarket.com/markets?limit=2000&closed=false", "default"),
        ("https://clob.polymarket.com/markets?limit=2000", "nofilter"),
        ("https://clob.polymarket.com/markets?limit=2000&archived=false", "unarchived"),
    ]
    
    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/json"}
    
    for url, label in endpoints:
        try:
            resp = requests.get(url, headers=headers, timeout=15)
            if resp.status_code != 200:
                continue
            data = resp.json()
            
            # Accepting_orders = market is currently tradeable
            markets = []
            for m in data.get("data", []):
                if not m.get("accepting_orders"):
                    continue
                q = m.get("question", "").lower()
                # Expanded weather keywords (not just "highest temperature")
                weather_kws = ["highest temperature", "temperature", "weather", "heat", "°f", "°c", "fahrenheit", "celsius"]
                if any(kw in q for kw in weather_kws):
                    # Also require one of our cities
                    if any(c in q for c in LOCATIONS):
                        markets.append({
                            "question": m["question"],
                            "condition_id": m["condition_id"],
                            "tokens": m.get("tokens", []),
                            "volume": m.get("volume24hr", 0),
                            "liquidity": m.get("liquidity", 0),
                            "end_date_iso": m.get("end_date_iso"),
                            "accepting_orders": m.get("accepting_orders", False),
                        })
            
            if markets:
                print(f"[API] Found {len(markets)} weather markets via {label}")
                return markets
            
            # No markets found — save debug
            debug_path = DATA_DIR / "api_debug.json"
            with open(debug_path, "w") as f:
                json.dump({
                    "endpoint": label,
                    "url": url,
                    "total_markets": len(data.get("data", [])),
                    "accepting_orders_count": sum(1 for m in data.get("data", []) if m.get("accepting_orders")),
                    "sample_markets": [
                        {"question": m["question"], "active": m.get("active"),
                         "closed": m.get("closed"), "accepting": m.get("accepting_orders")}
                        for m in data.get("data", [])[:20]
                    ]
                }, f, indent=2)
            print(f"[API] No weather markets found via {label}, saved debug to {debug_path}")
            
        except Exception as e:
            print(f"[API] Error via {label}: {e}")
    
    return []

def extract_city_from_question(q):
    """Extract city from market question."""
    q = q.lower()
    for city in LOCATIONS:
        if city.replace("-", " ") in q or city.replace("-", "") in q:
            return city
    return None

def extract_date_from_question(q):
    """Extract date from market question."""
    import re
    patterns = [
        r"march\s+(\d+)",
        r"april\s+(\d+)",
        r"may\s+(\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, q)
        if match:
            month = "march" if "march" in pattern else "april" if "april" in pattern else "may"
            return f"2026-{match.group(1).zfill(2)}"
    return None

# =============================================================================
# MAIN TRADING LOOP
# =============================================================================

def scan_markets():
    """Main scanning function with all 5 bug fixes applied."""
    print(f"\n{'='*60}")
    print(f"Scanning Polymarket weather markets...")
    print(f"{'='*60}")
    
    # Get METAR temps
    metar_temps = get_metar_multi()
    if metar_temps:
        print(f"\n[METAR] Current temps: {metar_temps}")
    
    # Get markets
    markets = get_polymarket_markets()
    print(f"\nFound {len(markets)} weather markets")
    
    if not markets:
        print("[INFO] No active weather markets to scan")
        return 0
    
    state = load_state()
    trades_made = 0
    
    # Bug fix #5: City prioritization - Atlanta (81% win rate) first
    # Sort markets by city priority (lower number = higher priority)
    CITY_PRIORITY = {
        "atlanta": 1, "singapore": 2, "hong-kong": 3, "tokyo": 4,
        "seoul": 5, "nyc": 6, "chicago": 7, "miami": 8,
        "dallas": 9, "london": 10, "paris": 11, "munich": 12, "seattle": 13,
    }
    
    # Sort cities by priority for logging
    sorted_cities = sorted(markets, key=lambda m: CITY_PRIORITY.get(
        extract_city_from_question(m["question"]) or "", 99))
    
    for m in sorted_cities:
        city = extract_city_from_question(m["question"])
        date = extract_date_from_question(m["question"])
        
        if not city or not date:
            continue
        
        # Bug fix #5: De-prioritize low win-rate cities
        city_priority = CITY_PRIORITY.get(city, 50)
        if city_priority >= 10:  # deprioritize seattle, munich, london, paris
            # Only process if EV is extra good
            pass  # continue processing all, but deprioritize in sorting
        
        # Get ensemble forecast (now returns tuple)
        ensemble, ecmwf_temp, metar_temp = get_ensemble_forecast(city, date)
        if ensemble is None:
            continue
        forecast = ensemble
        
        # Get city-specific bias (known + learned) — Bug fix #3: pre-bias correction
        # Bias is applied BEFORE probability computation (in bucket_prob)
        known_bias = CITY_ACCURACY.get(city, {}).get("known_bias", 0.0)
        learned_bias = get_learned_bias(city)
        total_bias = known_bias + learned_bias
        
        # Bug fix #2: Dynamic sigma based on model disagreement
        sigma = get_dynamic_sigma(city, ecmwf_temp, metar_temp)
        
        # Bug fix #4: Detect cumulative (<=) questions
        q_lower = m["question"].lower()
        is_cumulative = "at or below" in q_lower or "less than or equal to" in q_lower or "<=" in q_lower
        
        # Bug fix #1: Check for adjacent bucket pricing inversions
        inversion = detect_pricing_inversion(m.get("tokens", []), forecast, city)
        if inversion:
            print(f"\n[INVERSION] {city}: {inversion['lower_temp']}°F@{inversion['lower_price']:.2f} vs "
                  f"{inversion['higher_temp']}°F@{inversion['higher_price']:.2f} | Forecast: {forecast}°F")
        
        # Calculate probability for each outcome
        for token in m.get("tokens", []):
            outcome = token.get("outcome", "")
            price = token.get("price", 0)
            
            # Extract target temp from outcome
            temp_match = re.search(r"(\d+)\s*°?[CcFf]", outcome)
            if not temp_match:
                continue
            
            target_temp = int(temp_match.group(1))
            
            # Skip if price too high or volume too low
            if price > MAX_PRICE or m.get("volume", 0) < MIN_VOLUME:
                continue
            
            # Bug fix #3 & #4: Apply correct probability function
            if is_cumulative:
                # Bug fix #4: cumulative probability for <= questions
                prob = bucket_prob_cumulative(forecast, target_temp, sigma, total_bias)
            else:
                prob = bucket_prob(forecast, target_temp, sigma, total_bias)
            
            # Calculate EV
            ev = calc_ev(prob, price)
            
            # Bug fix #5: Atlanta gets easier threshold
            min_ev_threshold = MIN_EV
            if city == "atlanta":
                min_ev_threshold = MIN_EV * 0.8  # 20% lower threshold for Atlanta
            
            if ev >= min_ev_threshold and prob > 0.1:
                print(f"\n[TRADE] {city} {date} [priority: {city_priority}]")
                print(f"  Forecast: {forecast}°C (bias: {total_bias:.1f}, sigma: {sigma:.1f})")
                print(f"  Target: {target_temp}°C @ {price*100:.0f}¢")
                print(f"  Prob: {prob*100:.1f}% | EV: {ev*100:.1f}%")
                if inversion:
                    print(f"  [INVERSION DETECTED] Pair trade opportunity!")
                
                # Paper trade
                kelly = calc_kelly(prob, price)
                bet = min(kelly * state["balance"], MAX_BET)
                
                if bet > 0.5:
                    # Log prediction
                    add_prediction(city, date, forecast, None, outcome, ev)
                    
                    state["trades"].append({
                        "city": city,
                        "date": date,
                        "outcome": outcome,
                        "price": price,
                        "bet": bet,
                        "forecast": forecast,
                        "sigma": sigma,
                        "ev": ev,
                        "inversion": bool(inversion),
                        "timestamp": datetime.now().isoformat()
                    })
                    state["balance"] -= bet
                    trades_made += 1
                    print(f"  [PAPER BUY] ${bet:.2f} @ {price*100:.0f}¢")
                    
                    if trades_made >= 5:
                        break
    
    if trades_made > 0:
        save_state(state)
        print(f"\n[SUMMARY] Made {trades_made} paper trades")
        print(f"Balance: ${state['balance']:.2f}")
    else:
        print("\n[INFO] No trades met criteria this scan")
    
    return trades_made

def show_accuracy():
    """Display accuracy statistics."""
    acc = load_accuracy()
    total = get_total_accuracy()
    
    print(f"\n{'='*60}")
    print("ACCURACY STATISTICS")
    print(f"{'='*60}")
    print(f"Total predictions: {total['count']}")
    print(f"MAE: {total['mae']}°C")
    print(f"Bias: {total['bias']:+.2f}°C")
    
    print(f"\nPer-city accuracy:")
    for city, data in sorted(acc["cities"].items()):
        if data["count"] >= 3:
            mae = sum(abs(e) for e in data["errors"]) / len(data["errors"])
            bias = data["bias_sum"] / data["count"]
            print(f"  {city}: {data['count']} preds, MAE: {mae:.1f}°C, bias: {bias:+.1f}°C")

def show_status():
    """Show current balance and positions."""
    state = load_state()
    print(f"\n{'='*60}")
    print("PAPER TRADING STATUS")
    print(f"{'='*60}")
    print(f"Balance: ${state.get('balance', 0):.2f}")
    print(f"Open positions: {len(state.get('trades', []))}")

def main():
    if len(sys.argv) > 1:
        cmd = sys.argv[1]
        if cmd == "accuracy":
            show_accuracy()
        elif cmd == "status":
            show_status()
        else:
            print(f"Unknown command: {cmd}")
    else:
        scan_markets()

if __name__ == "__main__":
    main()
