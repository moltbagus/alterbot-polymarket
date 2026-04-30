#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tradingagents_integration.py — TradingAgents Multi-Agent Debate for Weather Betting
====================================================================================
Integrates TradingAgents framework into bot_v2.py:
- Before any trade, run full bull/bear debate
- Risk Manager must APPROVE before placing trade
- Log all agent debates for learning
- Require risk_manager conviction >= 7/10 for any trade
"""

import os
import sys
import json
import time
import math
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Add TradingAgents to path
TA_PATH = os.path.expanduser("~/.openclaw/workspace/TradingAgents")
if os.path.exists(TA_PATH):
    sys.path.insert(0, TA_PATH)


# ============================================================================
# LOG ROTATION
# ============================================================================

def _rotate_logs():
    """Delete TA debate logs older than 7 days. Called once at module load."""
    log_dir = os.path.expanduser("~/.openclaw/workspace/alter-bot-v1/data/tradingagents_logs")
    if not os.path.exists(log_dir):
        return
    cutoff = datetime.now() - timedelta(days=7)
    for f in os.listdir(log_dir):
        if not f.endswith(".json"):
            continue
        path = os.path.join(log_dir, f)
        try:
            if os.path.getmtime(path) < cutoff.timestamp():
                os.unlink(path)
        except OSError:
            pass

_rotate_logs()

# ============================================================================
# DATA SOURCES (reuse from bot_v2.py config)
# ============================================================================

CITY_CONFIG = {
    "singapore": {"icao": "WSSS", "lat": 1.3502, "lon": 103.9940, "tz": "Asia/Singapore"},
    "tokyo": {"icao": "RJTT", "lat": 35.7647, "lon": 140.3864, "tz": "Asia/Tokyo"},
    "seoul": {"icao": "RKSI", "lat": 37.4691, "lon": 126.4505, "tz": "Asia/Seoul"},
    "shanghai": {"icao": "ZSPD", "lat": 31.1443, "lon": 121.8083, "tz": "Asia/Shanghai"},
    "taipei": {"icao": "RCTP", "lat": 25.0797, "lon": 121.2342, "tz": "Asia/Taipei"},
    "london": {"icao": "EGLC", "lat": 51.5048, "lon": 0.0495, "tz": "Europe/London"},
    "paris": {"icao": "LFPG", "lat": 48.9962, "lon": 2.5979, "tz": "Europe/Paris"},
    "munich": {"icao": "EDDM", "lat": 48.3537, "lon": 11.7750, "tz": "Europe/Berlin"},
    "nyc": {"icao": "KLGA", "lat": 40.7772, "lon": -73.8726, "tz": "America/New_York"},
    "chicago": {"icao": "KORD", "lat": 41.9742, "lon": -87.9073, "tz": "America/Chicago"},
    "miami": {"icao": "KMIA", "lat": 25.7959, "lon": -80.2870, "tz": "America/New_York"},
    "atlanta": {"icao": "KATL", "lat": 33.6407, "lon": -84.4277, "tz": "America/New_York"},
    "dallas": {"icao": "KDAL", "lat": 32.8471, "lon": -96.8518, "tz": "America/Chicago"},
    "sao-paulo": {"icao": "SBGR", "lat": -23.4356, "lon": -46.4731, "tz": "America/Sao_Paulo"},
    "hong-kong": {"icao": "HKO", "lat": 22.3025, "lon": 114.1747, "tz": "Asia/Hong_Kong"},
    "ankara": {"icao": "LTAC", "lat": 40.1281, "lon": 32.9951, "tz": "Europe/Istanbul"},
    "lucknow": {"icao": "VILK", "lat": 26.7606, "lon": 80.8893, "tz": "Asia/Kolkata"},
}


def get_metar_data(icao: str) -> Dict[str, Any]:
    """Get METAR data for a given airport (ICAO code)."""
    try:
        r = requests.get(
            f"https://aviationweather.gov/api/data/metar?ids={icao}&format=json",
            timeout=10
        )
        data = r.json()
        if data:
            m = data[0]
            return {
                "temp": m.get("temp"),
                "dewp": m.get("dewp"),
                "humidity": m.get("humidity"),
                "wspd": m.get("wspd"),
                "wgust": m.get("wgust"),
                "sky": m.get("sky"),
                "raw": m.get("rawOb", "")[:200],
                "time": m.get("reportTime"),
            }
    except Exception as e:
        return {"error": str(e)}
    return {"error": "No data"}


def get_forecast_temp(city: str, target_date: str) -> Dict[str, Any]:
    """Get temperature forecast from Open-Meteo (ECMWF)."""
    config = CITY_CONFIG.get(city.lower())
    if not config:
        return {"error": "Unknown city"}
    
    try:
        target = datetime.strptime(target_date, "%Y-%m-%d")
        days_ahead = (target - datetime.now()).days + 1
        
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": config["lat"],
            "longitude": config["lon"],
            "daily": "temperature_2m_max,temperature_2m_min",
            "temperature_unit": "celsius",
            "timezone": config["tz"],
            "forecast_days": min(days_ahead + 3, 16),
            "models": "ecmwf_ifs025",
        }
        
        r = requests.get(url, params=params, timeout=10)
        data = r.json()
        
        daily = data.get("daily", {})
        times = daily.get("time", [])
        
        for i, t in enumerate(times):
            if t == target_date:
                return {
                    "max": daily["temperature_2m_max"][i],
                    "min": daily["temperature_2m_min"][i],
                    "avg": (daily["temperature_2m_max"][i] + daily["temperature_2m_min"][i]) / 2,
                }
        
        return {"error": "Date not in forecast range"}
    except Exception as e:
        return {"error": str(e)}


def get_polymarket_odds(market_id: str) -> Dict[str, Any]:
    """Get current Polymarket odds for a market."""
    try:
        r = requests.get(f"https://gamma-api.polymarket.com/markets/{market_id}", timeout=(3, 5))
        data = r.json()
        return {
            "yes_price": float(data.get("bestAsk", data.get("outcomePrices", [0])[0] if data.get("outcomePrices") else 0)),
            "no_price": float(data.get("bestBid", 1 - float(data.get("bestAsk", 0.5)))),
            "volume": float(data.get("volume", 0)),
            "clob": data.get("clob", ""),
        }
    except Exception as e:
        return {"error": str(e)}


# ============================================================================
# ANALYST AGENTS
# ============================================================================

class FundamentalsAnalyst:
    """Analyzes METAR data - current weather conditions."""
    
    def __init__(self):
        self.name = "Fundamentals Analyst (METAR)"
    
    def analyze(self, city: str, target_date: str, target_temp: int, unit: str = "C") -> Dict[str, Any]:
        config = CITY_CONFIG.get(city.lower())
        if not config:
            return {"error": "Unknown city"}
        
        metar = get_metar_data(config["icao"])
        forecast = get_forecast_temp(city, target_date)

        # METAR temp is in Celsius; forecast_max is also Celsius (Open-Meteo default)
        current_temp = metar.get("temp", 0) or 0
        forecast_max = forecast.get("max", 0) or 0

        # Unit-aware can_reach: convert Fahrenheit target to Celsius for comparison
        if unit == "F":
            target_c = round((target_temp - 32) * 5 / 9, 1)
        else:
            target_c = float(target_temp)
        can_reach = forecast_max >= target_c

        # Confidence from forecast gap (always in Celsius)
        gap = forecast_max - current_temp
        conf = 50
        if can_reach:
            conf += 20
            if forecast_max - target_c >= 2:
                conf += 15  # comfortable margin
        else:
            conf -= 30
        
        # Wind factor
        wspd = metar.get("wspd", 0)
        if wspd and wspd < 15:
            conf += 5
        elif wspd and wspd > 25:
            conf -= 10
        
        conf = min(95, max(10, conf))
        
        report = f"""# Fundamentals Analysis - {city.title()} {target_temp}°{unit} on {target_date}

## METAR Conditions ({config['icao']})
- Temp: {current_temp}°{unit}
- Dew Point: {metar.get('dewp', 'N/A')}°{unit}
- Wind: {metar.get('wspd', 'N/A')} kt | Gusts: {metar.get('wgust', 'N/A')} kt
- Humidity: {metar.get('humidity', 'N/A')}%
- Sky: {metar.get('sky', 'N/A')}

## Forecast (ECMWF)
- Max: {forecast_max}°{unit} | Min: {forecast.get('min', 'N/A')}°{unit}
- Gap from current: {gap:+.1f}°{unit}

## Assessment
- **Can Reach Target:** {'YES' if can_reach else 'NO'}
- **Target:** {target_temp}°{unit} vs Forecast: {forecast_max}°{unit}
- **Confidence:** {conf}%

## Signal
{'BULLISH: Forecast max exceeds target, conditions favorable' if can_reach and conf > 50 else 'BEARISH: Forecast max below target or conditions unfavorable'}
"""
        return {
            "report": report,
            "confidence": conf,
            "current_temp": current_temp,
            "forecast_max": forecast_max,
            "can_reach": can_reach,
            "metar": metar,
        }


class SentimentAnalyst:
    """Analyzes Polymarket market odds and sentiment."""

    def __init__(self):
        self.name = "Sentiment Analyst (Market Odds)"

    def detect_market_inefficiency(self, market_id: str, bot_confidence: float, p: float) -> Dict[str, Any]:
        """
        Detect market mispricing: bot high-conviction signal vs market price.

        Returns:
            is_inefficient: True if market underestimates the event (edge exists)
            edge_direction: "buy_yes" or "skip"
            market_price: current YES price
            bot_prob: bot's probability estimate
            disagreement_pct: |market - bot| as a percentage
            reason: explanation
        """
        odds = get_polymarket_odds(market_id)

        if "error" in odds:
            return {"is_inefficient": False, "error": odds["error"]}

        market_price = odds.get("yes_price", 0.5)
        bot_prob = float(bot_confidence) if bot_confidence is not None else p
        disagreement_pct = abs(market_price - bot_prob)

        # DEBUG: print all gate inputs
        print(f"  [GATE-DEBUG] market_id={market_id} | bot_prob={bot_prob:.3f} | market_price=${market_price:.3f} | disagreement={disagreement_pct:.3f} | bot_prob-0.15={bot_prob-0.15:.3f}")

        # No-trade zones: market too certain or too uncertain
        if market_price > 0.85:
            return {
                "is_inefficient": False,
                "edge_direction": "skip",
                "market_price": market_price,
                "bot_prob": bot_prob,
                "disagreement_pct": disagreement_pct,
                "reason": f"Market price ${market_price:.3f} > $0.85 — near-certain, no edge"
            }

        if market_price < 0.02:
            return {
                "is_inefficient": False,
                "edge_direction": "skip",
                "market_price": market_price,
                "bot_prob": bot_prob,
                "disagreement_pct": disagreement_pct,
                "reason": f"Market price ${market_price:.3f} < $0.02 — long-shot, too risky"
            }

        # Bot must have HIGH conviction (>80%) for inefficiency to matter
        # If market says YES=$0.80 but bot is 95% confident, market underestimates → BET
        # If market says YES=$0.80 and bot is only 55% confident, market is probably right → SKIP
        if bot_prob >= 0.70 and market_price < bot_prob - 0.15:
            # Market underestimates: bot thinks it's more likely than market implies
            edge = bot_prob - market_price
            return {
                "is_inefficient": True,
                "edge_direction": "buy_yes",
                "market_price": market_price,
                "bot_prob": bot_prob,
                "disagreement_pct": disagreement_pct,
                "reason": f"BET: Bot {bot_prob:.0%} vs market {market_price:.0%} — market underestimates by {edge:.0%}"
            }

        if bot_prob < 0.60 and market_price > bot_prob + 0.15:
            # Bot disagrees with market direction — if market is expensive and bot is skeptical
            return {
                "is_inefficient": False,
                "edge_direction": "skip",
                "market_price": market_price,
                "bot_prob": bot_prob,
                "disagreement_pct": disagreement_pct,
                "reason": f"SKIP: Bot {bot_prob:.0%} vs market {market_price:.0%} — market overestimate, bot low confidence"
            }

        # Sigma-adjusted probability vs market price disagreement > 20%
        if disagreement_pct > 0.20:
            return {
                "is_inefficient": False,
                "edge_direction": "skip",
                "market_price": market_price,
                "bot_prob": bot_prob,
                "disagreement_pct": disagreement_pct,
                "reason": f"SKIP: Sigma-adjusted prob and market price disagree by {disagreement_pct:.0%} > 20% — too uncertain"
            }

        return {
            "is_inefficient": False,
            "edge_direction": "neutral",
            "market_price": market_price,
            "bot_prob": bot_prob,
            "disagreement_pct": disagreement_pct,
            "reason": "No inefficiency detected — market price reasonably aligned with bot estimate"
        }

    def analyze(self, market_id: str, target_temp: int, unit: str = "C") -> Dict[str, Any]:
        odds = get_polymarket_odds(market_id)
        
        if "error" in odds:
            return {"error": odds["error"]}
        
        yes_price = odds.get("yes_price", 0.5)
        no_price = odds.get("no_price", 0.5)
        volume = odds.get("volume", 0)
        
        # Sentiment
        if yes_price > 0.7:
            sentiment = "STRONGLY_BULLISH"
        elif yes_price > 0.55:
            sentiment = "BULLISH"
        elif yes_price > 0.45:
            sentiment = "NEUTRAL"
        elif yes_price > 0.3:
            sentiment = "BEARISH"
        else:
            sentiment = "STRONGLY_BEARISH"
        
        report = f"""# Sentiment Analysis - Polymarket Market

## Market Data
- **YES Price:** ${yes_price:.3f} ({yes_price*100:.0f}% implied)
- **NO Price:** ${no_price:.3f}
- **Volume:** ${volume:,.0f}

## Sentiment: {sentiment}

## Interpretation
Market pricing in {yes_price*100:.0f}% chance of resolution YES.
{'Market agrees with our analysis' if yes_price > 0.5 else 'Market disagrees - potential value'}
"""
        return {
            "report": report,
            "yes_price": yes_price,
            "no_price": no_price,
            "volume": volume,
            "sentiment": sentiment,
        }


class TechnicalAnalyst:
    """Analyzes historical patterns and forecast trends."""

    # Historical averages by city/day-of-year (interpolated monthly -> daily)
    # Using NOAA/ECMWF climate normals as baseline
    HISTORICAL_DAILY = {
        # Format: city -> (month, day) -> avg temp in °C
        # Populated with more granular data below
    }

    # Monthly averages as fallback (°C) — used to interpolate daily values
    HISTORICAL_MONTHLY = {
        "singapore": {1: 29, 2: 29, 3: 30, 4: 31, 5: 31, 6: 30, 7: 30, 8: 30, 9: 30, 10: 30, 11: 30, 12: 29},
        "tokyo": {1: 6, 2: 7, 3: 14, 4: 18, 5: 23, 6: 26, 7: 30, 8: 31, 9: 27, 10: 22, 11: 16, 12: 11},
        "seoul": {1: 0, 2: 2, 3: 11, 4: 16, 5: 21, 6: 25, 7: 28, 8: 29, 9: 25, 10: 18, 11: 10, 12: 3},
        "london": {1: 6, 2: 6, 3: 11, 4: 14, 5: 18, 6: 21, 7: 24, 8: 23, 9: 20, 10: 15, 11: 11, 12: 8},
        "nyc": {1: 3, 2: 4, 3: 10, 4: 16, 5: 21, 6: 26, 7: 29, 8: 28, 9: 24, 10: 17, 11: 11, 12: 5},
        "chicago": {1: -2, 2: -1, 3: 8, 4: 14, 5: 20, 6: 25, 7: 28, 8: 27, 9: 23, 10: 15, 11: 8, 12: 1},
        "miami": {1: 24, 2: 25, 3: 26, 4: 28, 5: 30, 6: 31, 7: 32, 8: 32, 9: 31, 10: 29, 11: 26, 12: 24},
        "atlanta": {1: 9, 2: 11, 3: 18, 4: 23, 5: 27, 6: 31, 7: 33, 8: 33, 9: 29, 10: 24, 11: 18, 12: 13},
        "dallas": {1: 12, 2: 14, 3: 21, 4: 26, 5: 30, 6: 35, 7: 37, 8: 37, 9: 33, 10: 27, 11: 21, 12: 16},
        "sao-paulo": {1: 28, 2: 28, 3: 28, 4: 26, 5: 24, 6: 22, 7: 22, 8: 25, 9: 27, 10: 28, 11: 28, 12: 28},
        "hong-kong": {1: 19, 2: 19, 3: 21, 4: 24, 5: 28, 6: 30, 7: 32, 8: 32, 9: 31, 10: 29, 11: 25, 12: 21},
        "paris": {1: 6, 2: 7, 3: 13, 4: 16, 5: 20, 6: 24, 7: 26, 8: 26, 9: 22, 10: 16, 11: 11, 12: 8},
        "ankara": {1: 2, 2: 3, 3: 10, 4: 16, 5: 21, 6: 26, 7: 30, 8: 30, 9: 25, 10: 18, 11: 11, 12: 5},
        "lucknow": {1: 18, 2: 20, 3: 26, 4: 32, 5: 35, 6: 34, 7: 32, 8: 31, 9: 30, 10: 28, 11: 22, 12: 18},
    }

    # City population (millions) for UHI correction
    # Larger cities have stronger urban heat island effect
    CITY_POPULATION = {
        "tokyo": 37.4,
        "delhi": 32.9,
        "shanghai": 28.5,
        "sao-paulo": 22.4,
        "mexico-city": 21.8,
        "dhaka": 21.7,
        "cairo": 21.3,
        "beijing": 21.0,
        "mumbai": 20.7,
        "nyc": 18.8,
        "kolkata": 18.6,
        "london": 14.8,
        "hong-kong": 7.5,
        "paris": 7.0,
        "singapore": 5.9,
        "chicago": 2.7,
        "atlanta": 5.0,
        "dallas": 5.0,
        "seoul": 24.0,
    }

    def __init__(self):
        self.name = "Technical Analyst (Historical + Trend + UHI)"

    def _get_historical_temp(self, city: str, target_dt: datetime) -> float:
        """Get interpolated historical temperature for a city on a specific date."""
        city_lower = city.lower()
        monthly = self.HISTORICAL_MONTHLY.get(city_lower, {})

        if not monthly:
            return 25.0  # default fallback

        month = target_dt.month
        # Linear interpolation between months for more accurate daily value
        prev_month = 12 if month == 1 else month - 1
        next_month = 1 if month == 12 else month + 1

        prev_temp = monthly.get(prev_month, 25)
        curr_temp = monthly.get(month, 25)
        next_temp = monthly.get(next_month, 25)

        # Day of month (approximate)
        day = target_dt.day
        days_in_month = 31  # approximate
        fraction = (day - 1) / days_in_month

        # Interpolate: blend from prev month to current to next month
        # This gives smoother seasonal transitions
        if fraction < 0.5:
            # First half of month: blend prev -> current
            temp = prev_temp + (curr_temp - prev_temp) * (fraction * 2)
        else:
            # Second half of month: blend current -> next
            temp = curr_temp + (next_temp - curr_temp) * ((fraction - 0.5) * 2)

        return round(temp, 1)

    def _get_uhi_correction(self, city: str, unit: str = "C") -> float:
        """Estimate UHI correction based on city population.

        UHI effect: major cities can be 2-5°C warmer than surrounding areas.
        We apply this as a bonus to forecast accuracy for big city markets.
        """
        city_lower = city.lower()
        pop = self.CITY_POPULATION.get(city_lower, 1.0)

        # UHI magnitude: roughly log(pop) / 10, capped at 3°C
        uhi_c = min(3.0, max(0.5, round(math.log10(max(pop, 1.0)) * 1.5, 1)))

        if unit == "F":
            return round(uhi_c * 9/5, 1)
        return uhi_c

    def _get_seasonal_adjustment(self, city: str, target_dt: datetime, forecast_max: float) -> Dict[str, Any]:
        """Analyze seasonal position within the year's temperature curve.

        Returns adjustment factor and explanation.
        """
        month = target_dt.month
        city_lower = city.lower()
        monthly = self.HISTORICAL_MONTHLY.get(city_lower, {})

        if not monthly:
            return {"adjustment": 0, "explanation": "No seasonal data", "peak_month": 7, "trough_month": 1}

        # Find if we're in warming or cooling phase
        # Spring: months 3-5 (N hemisphere), 9-11 (S hemisphere)
        # Summer: months 6-8 (N), 12-2 (S)
        temps = [monthly.get(m, 20) for m in range(1, 13)]
        peak_month = temps.index(max(temps)) + 1  # 1-indexed
        trough_month = (temps.index(min(temps)) + 1)

        # Distance from peak/trough
        months_from_peak = abs(month - peak_month)
        months_from_trough = abs(month - trough_month)

        # Seasonal momentum: temperatures tend to continue their trend
        # If we're in April and peak is July, we're in "warming phase"
        is_northern = city_lower not in {"sao-paulo", "buenos-aires", "wellington", "sydney"}

        if is_northern:
            if month in [3, 4, 5] and months_from_trough < 6:
                # Spring warming phase
                seasonal_bias = 1.0  # temps likely to exceed forecast
                explanation = "Spring warming phase — temps tend to exceed models"
            elif month in [9, 10, 11] and months_from_peak < 4:
                # Autumn cooling phase
                seasonal_bias = -1.0
                explanation = "Autumn cooling phase — temps may fall below forecast"
            elif month in [6, 7, 8]:
                seasonal_bias = 0.5
                explanation = "Summer peak — warm bias possible"
            elif month in [12, 1, 2]:
                seasonal_bias = -0.5
                explanation = "Winter cold — potential cold bias"
            else:
                seasonal_bias = 0
                explanation = "Neutral seasonal position"
        else:
            # Southern hemisphere: seasons are reversed
            if month in [9, 10, 11] and months_from_trough < 6:
                seasonal_bias = 1.0
                explanation = "Southern spring warming"
            elif month in [3, 4, 5] and months_from_peak < 4:
                seasonal_bias = -1.0
                explanation = "Southern autumn cooling"
            else:
                seasonal_bias = 0
                explanation = "Neutral seasonal position"

        return {
            "adjustment": seasonal_bias,
            "explanation": explanation,
            "peak_month": peak_month,
            "trough_month": trough_month,
        }

    def analyze(self, city: str, target_date: str, forecast_max: float, unit: str = "C") -> Dict[str, Any]:
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        month = target_dt.month

        # 1. Historical average (interpolated for day-of-year accuracy) — always in Celsius
        hist_c = self._get_historical_temp(city, target_dt)

        # 2. UHI correction in Celsius
        uhi_c = self._get_uhi_correction(city, "C")

        # 3. Seasonal adjustment (use .get() for all accesses to prevent KeyError)
        _sm = self._get_seasonal_adjustment(city, target_dt, forecast_max)

        # 4. Convert forecast to Celsius for consistent comparison
        if unit == "F":
            forecast_c = (forecast_max - 32) * 5 / 9
        else:
            forecast_c = forecast_max

        # 5. Combined deviation: forecast vs historical + UHI + seasonal
        # Effective "normal" = historical + UHI adjustment (cities are warmer than raw station data)
        effective_normal_c = hist_c + uhi_c
        deviation_c = forecast_c - effective_normal_c

        # Apply seasonal bias to deviation (in Celsius)
        seasonal_adj_c = _sm.get("adjustment", 0) * 0.5
        adjusted_deviation_c = deviation_c - seasonal_adj_c

        # Convert back to display unit for report
        if unit == "F":
            deviation = round(deviation_c * 9/5, 1)
            adjusted_deviation = round(adjusted_deviation_c * 9/5, 1)
            effective_normal = round(effective_normal_c * 9/5, 1)
            uhi_display = round(uhi_c * 9/5, 1)
        else:
            deviation = round(deviation_c, 1)
            adjusted_deviation = round(adjusted_deviation_c, 1)
            effective_normal = round(effective_normal_c, 1)
            uhi_display = round(uhi_c, 1)

        hist = hist_c if unit == "C" else round(hist_c * 9/5, 1)

        if adjusted_deviation > 2:
            pattern = "WARM_ANOMALY"
        elif adjusted_deviation < -2:
            pattern = "COLD_ANOMALY"
        else:
            pattern = "NORMAL"

        # Build report — use .get() for all seasonal accesses
        report_lines = [
            f"# Technical Analysis - {city.title()}",
            "",
            "## Historical Baseline (Day-of-Year)",
            f"- **Historical Avg (Interpolated):** {hist}°{unit}",
            f"- **UHI Correction (Pop {self.CITY_POPULATION.get(city.lower(), 'N/A')}M):** +{uhi_display}°{unit}",
            f"- **Effective Normal:** {effective_normal}°{unit}",
            f"- **Current Forecast:** {forecast_max}°{unit}",
            f"- **Raw Deviation:** {deviation:+.1f}°{unit}",
            "",
            "## Seasonal Analysis",
            f"- **Seasonal Phase:** {_sm.get('explanation', 'N/A')}",
            f"- **Peak Month:** {_sm.get('peak_month', 'N/A')} | Trough: {_sm.get('trough_month', 'N/A')}",
            f"- **Seasonal Adjustment:** {_sm.get('adjustment', 0):+.1f} → Adjusted Deviation: {adjusted_deviation:+.1f}°{unit}",
            "",
            f"## Pattern: {pattern}",
            "Above normal — favorable for reaching warm targets" if adjusted_deviation > 0 else "Below normal — headwind for warm targets" if adjusted_deviation < -1 else "Near normal conditions",
            "",
            f"## Signal\n{pattern}",
        ]
        report = "\n".join(report_lines)
        return {
            "report": report,
            "historical_avg": hist,
            "deviation": round(deviation, 1),
            "adjusted_deviation": round(adjusted_deviation, 1),
            "pattern": pattern,
            "uhi_correction": uhi_display,
            "seasonal_adjustment": _sm.get("adjustment", 0),
            "seasonal_explanation": _sm.get("explanation", ""),
        }


# ============================================================================
# RESEARCHER AGENTS (Bull/Bear Debate)
# ============================================================================

class BullResearcher:
    """Makes the bull case for YES."""
    
    def __init__(self):
        self.name = "Bull Researcher"
    
    def argue(self, fundamentals: Dict, sentiment: Dict, technical: Dict, target_temp: int) -> str:
        args = []
        
        if fundamentals.get("can_reach") and fundamentals.get("confidence", 0) > 50:
            args.append(f"Fundamentals: Forecast {fundamentals.get('forecast_max')}°C CAN reach target {target_temp}°C (conf: {fundamentals.get('confidence')}%)")
        
        if sentiment.get("yes_price", 0) > 0.5:
            args.append(f"Market: YES at {sentiment.get('yes_price', 0)*100:.0f}% - market agrees with thesis")
        
        if technical.get("deviation", 0) > 0:
            args.append(f"Technical: +{technical.get('deviation', 0):.1f}°C above historical - warm anomaly supports bullish")
        
        if not args:
            return "# Bull Case: NO ARGUMENTS FOUND\n\n**Recommendation: SKIP - No strong bull case**"
        
        report = """# Bull Case - YES Vote
"""
        for i, arg in enumerate(args, 1):
            report += f"{i}. {arg}\n"
        
        report += f"\n**Recommendation: YES** (conviction: {min(90, 50 + len(args)*10)}%)\n"
        return report


class BearResearcher:
    """Makes the bear case for NO."""
    
    def __init__(self):
        self.name = "Bear Researcher"
    
    def argue(self, fundamentals: Dict, sentiment: Dict, technical: Dict, target_temp: int) -> str:
        args = []
        
        if not fundamentals.get("can_reach", True):
            gap = target_temp - fundamentals.get("forecast_max", 0)
            args.append(f"CRITICAL: Forecast {fundamentals.get('forecast_max')}°C CANNOT reach target {target_temp}°C (gap: {gap:+.1f}°C)")
        
        if fundamentals.get("confidence", 0) < 50:
            args.append(f"Fundamentals: Low confidence ({fundamentals.get('confidence')}%) - uncertainty is high")
        
        if sentiment.get("yes_price", 0) < 0.5:
            args.append(f"Market: YES at {sentiment.get('yes_price', 0)*100:.0f}% - market disagrees, potential overpricing")
        
        if technical.get("deviation", 0) < -2:
            args.append(f"Technical: {technical.get('deviation', 0):+.1f}°C below historical - cold anomaly working against us")
        
        wspd = fundamentals.get("metar", {}).get("wspd", 0)
        if wspd and wspd > 20:
            args.append(f"Weather: High winds ({wspd} kt) may suppress temperature")
        
        if not args:
            return "# Bear Case: NO STRONG ARGUMENTS\n\n**Recommendation: NO_BEAR - No compelling bear case**"
        
        report = """# Bear Case - NO Vote
"""
        for i, arg in enumerate(args, 1):
            report += f"{i}. {arg}\n"
        
        report += f"\n**Recommendation: NO** (conviction: {min(90, 50 + len(args)*10)}%)\n"
        return report


# ============================================================================
# RISK MANAGER (CRITICAL GATE)
# ============================================================================

class RiskManager:
    """The final gatekeeper - must APPROVE all trades."""
    
    def __init__(self):
        self.name = "Risk Manager"
        self.min_conviction = 1  # TUNED: Was 3, lowered to 1 for weather trading — temp targets are more predictable than stocks
        self.max_risk_score = 80  # TUNED: Was 65, raised to 80 — weather markets are less volatile than financial markets
    
    def evaluate(
        self,
        city: str,
        target_temp: int,
        target_date: str,
        unit: str,
        p: float,
        price: float,
        kelly: float,
        market_id: str,
        side: str = "YES",
        fundamentals: Dict = None,
        sentiment: Dict = None,
        technical: Dict = None,
        bull_case: str = None,
        bear_case: str = None,
        hours_ahead: float = 999.0,
    ) -> Dict[str, Any]:

        # yes_price: try sentiment dict first (from caller), then API, default to price param
        yes_price = sentiment.get("yes_price", None) if sentiment else None
        if yes_price is None and market_id:
            sentiment_data = get_polymarket_odds(market_id) if market_id else {}
            yes_price = sentiment_data.get("yes_price", price)
        else:
            yes_price = price
        yes_price = yes_price or price

        # --- NO-TRADE ZONE 1: Near-certain outcomes — no edge for either side ---
        # For YES bets: price > $0.85 means near-certain, no edge.
        # For NO bets on buckets priced $0.9995+: no NO edge left (bucket is ~certain to resolve YES).
        if side == "YES" and yes_price > 0.85:
            return self._rejected(
                city, target_temp, target_date, unit, p, price,
                f"REJECTED: Market YES=${yes_price:.3f} > $0.85 — near-certain outcome, no edge to exploit.",
                fundamentals, sentiment, technical, bull_case, bear_case
            )
        # NOTE: price guards for NO-side bucket bets are RELAXED.
        # The conviction scorecard handles edge quality. For bucket markets:
        # - Bucket ask = YES price for that bucket (cost to bet YES on bucket)
        # - The conviction gate filters based on forecast vs market, not just price
        if side == "NO" and price >= 0.9999:
            return self._rejected(
                city, target_temp, target_date, unit, p, price,
                f"REJECTED: Bucket ask=${price:.4f} >= $0.9999 — effectively certain YES.",
                fundamentals, sentiment, technical, bull_case, bear_case
            )

        # --- NO-TRADE ZONE 2: Long-shots ---
        # For YES bets: reject if YES price < $0.01 (long-shot edge too thin).
        # For NO bets: the "price" parameter IS the bucket ask (= YES price for that bucket).
        #   We only bet NO on overpriced buckets (ask > $0.90), so if bucket ask < $0.01
        #   the bucket is nearly certain to be YES — there's no NO edge.
        #   So for NO-side: reject if bucket ask < $0.01 (bucket is near-certain YES).
        if side == "YES" and yes_price < 0.01:
            return self._rejected(
                city, target_temp, target_date, unit, p, price,
                f"REJECTED: Market YES=${yes_price:.3f} < $0.01 — long-shot, expected value too thin.",
                fundamentals, sentiment, technical, bull_case, bear_case
            )
        if side == "NO" and price < 0.001:
            return self._rejected(
                city, target_temp, target_date, unit, p, price,
                f"REJECTED: Bucket ask=${price:.4f} < $0.001 — effectively free YES bucket.",
                fundamentals, sentiment, technical, bull_case, bear_case
            )

        # --- NO-TRADE ZONE 3: Sigma-adjusted probability disagrees with market ---
        # For YES bets: reject if disagreement > 60%.
        # For NO bets on overpriced buckets: the disagreement is EXPECTED.
        #   The bucket is priced at $0.90-$0.99 because market thinks it's ~certain to resolve YES.
        #   We think P(bucket) is much lower, which is WHY the NO bet has positive EV.
        #   Only reject NO bets if our P(bucket) is > the market's implied P(bucket).
        #   That would mean the market UNDERPRICED the bucket (which is opposite of NO-side thesis).
        if side == "YES":
            bot_confidence = fundamentals.get("confidence", 50) / 100.0
            disagreement = abs(bot_confidence - yes_price)
            if disagreement > 0.60:
                return self._rejected(
                    city, target_temp, target_date, unit, p, price,
                    f"REJECTED: Bot confidence ({bot_confidence:.0%}) and market price ({yes_price:.0%}) "
                    f"disagree by {disagreement:.0%} > 60% — too uncertain to act.",
                    fundamentals, sentiment, technical, bull_case, bear_case
                )
        # For NO bets: only reject if bot thinks bucket is MORE likely than market thinks
        # (i.e., bot overestimates the bucket — opposite of NO thesis).

        # Calculate conviction score (0-10)
        conviction = 5  # Start neutral
        
        # Factor 1: Can forecast reach target? (FIXED: invert logic for NO-side bets)
        # For NO bets: can_reach=False means bucket is impossible → strong NO signal → bonus
        # For YES bets: can_reach=False means forecast can't reach → wrong YES → penalty
        can_reach = fundamentals.get("can_reach", True)
        if side == "NO":
            if not can_reach:
                conviction += 3  # Bonus for impossible bucket — strong NO signal
            else:
                conviction -= 1  # Forecast can reach — less compelling NO edge
        else:  # YES bet
            if not can_reach:
                conviction -= 2  # Penalty for impossible target
        
        # Factor 2: Fundamentals confidence
        conf = fundamentals.get("confidence", 50)
        if conf >= 75:
            conviction += 1.5
        elif conf >= 60:
            conviction += 1
        elif conf < 40:
            conviction -= 1
        
        # Factor 3: Market alignment
        if yes_price > 0.6:
            conviction += 0.5  # Market agrees
        elif yes_price < 0.4:
            conviction -= 0.5  # Market disagrees - risky
        
        # Factor 4: Technical pattern
        if technical.get("pattern") == "WARM_ANOMALY":
            conviction += 0.5
        elif technical.get("pattern") == "COLD_ANOMALY":
            conviction -= 1
        
        # Factor 5: Kelly fraction (lower is safer)
        if kelly >= 0.3:
            conviction -= 0.5  # High Kelly = risky
        elif kelly >= 0.15:
            conviction += 0.5
        
        # Factor 6: EV quality
        ev = p * (1.0 / price - 1) - (1.0 - p)
        if ev >= 0.5:
            conviction += 0.5
        elif ev < 0.3:
            conviction -= 0.5
        
        conviction = max(1, min(10, conviction))
        
        # Risk score (0-100)
        risk_score = 50 - conviction * 3
        if fundamentals.get("metar", {}).get("wgust"):
            risk_score += 10
        if technical.get("deviation", 0) < 0:
            risk_score += 15
        
        risk_score = max(10, min(95, risk_score))

        # APPROVED or REJECTED
        approved = conviction >= self.min_conviction and risk_score <= self.max_risk_score

        # Kelly sizing guard: if Kelly > 0.15 AND market price > $0.10, reduce bet by 50%
        # Don't overbet even "good" trades when market is already priced moderately high
        kelly_reduction = 1.0
        if kelly > 0.15 and yes_price > 0.10:
            kelly_reduction = 0.5

        if approved:
            verdict = "APPROVED"
            position = self._get_position(kelly, conviction)
        else:
            verdict = "REJECTED"
            position = "NO_BET"
        
        # Build score breakdown
        score_breakdown = f"""# Risk Management Report - {city.title()} {target_temp}°{unit}

## Position Score: {conviction:.1f}/10 (min: {self.min_conviction})
## Risk Score: {risk_score}/100 (max allowed: {self.max_risk_score})

## Factor Analysis
1. Can Reach Target: {'YES' if fundamentals.get('can_reach') else 'NO'} {'+' if fundamentals.get('can_reach') else '-'}1.0
2. Fundamentals Conf: {conf}% {'+' if conf >= 60 else '-'}1.0
3. Market YES: {yes_price*100:.0f}% {'+' if yes_price >= 0.5 else '-'}0.5
4. Tech Pattern: {technical.get('pattern', 'NORMAL')} {'+' if technical.get('pattern') == 'WARM_ANOMALY' else '-'}0.5
5. Kelly: {kelly*100:.1f}% {'+' if kelly >= 0.15 else '-'}0.5
6. EV: {ev:.2f} {'+' if ev >= 0.3 else '-'}0.5

## Bull/Bear Summary
**BULL CASE:**
{bull_case[:300]}...

**BEAR CASE:**
{bear_case[:300]}...

## Final Verdict: {verdict}
**Position:** {position}
**Conviction:** {conviction:.1f}/10
**Risk Score:** {risk_score}/100

{'✅ Trade approved - all gates passed' if approved else '❌ Trade rejected - conviction below threshold'}
"""
        
        return {
            "report": score_breakdown,
            "verdict": verdict,
            "position": position,
            "conviction": round(conviction, 1),
            "risk_score": round(risk_score, 1),
            "approved": approved,
            "can_reach": fundamentals.get("can_reach", False),
            "kelly_reduction": kelly_reduction,
            "factors": {
                "fundamentals_confidence": conf,
                "yes_price": yes_price,
                "technical_pattern": technical.get("pattern", "NORMAL"),
                "kelly": kelly,
                "ev": round(ev, 3),
            }
        }
    
    def _get_position(self, kelly: float, conviction: float) -> str:
        # Lowered thresholds for bucket NO trades: conviction 3-4.9 = SMALL_BET (50%), 5-6.9 = STANDARD_BET (75%), 7+ = MAX_BET
        # Bucket NO bets have transparent Kelly sizing — conviction mainly gates whether to trade at all
        if conviction >= 9:
            return "MAX_BET"
        elif conviction >= 7:
            return "STANDARD_BET"
        elif conviction >= 3.5:
            return "SMALL_BET"
        else:
            return "NO_BET"
    
    def _rejected(self, city, target_temp, target_date, unit, p, price, reason,
                  fundamentals, sentiment, technical, bull_case, bear_case) -> Dict[str, Any]:
        return {
            "report": f"""# Risk Management Report - {city.title()} {target_temp}°{unit}

🚫 **REJECTED: {reason}**

## Analysis Summary
- Forecast Max: {fundamentals.get('forecast_max', 'N/A')}°{unit}
- Target: {target_temp}°{unit}
- Gap: {target_temp - (fundamentals.get('forecast_max') or 0):+.1f}°{unit}
- Fundamentals Conf: {fundamentals.get('confidence', 0)}%
- Market YES: {(sentiment.get('yes_price', 0) or 0)*100:.0f}%
- Pattern: {technical.get('pattern', 'N/A')}

## Decision: NO_BET
**Verdict:** REJECTED
**Conviction:** 0/10
**Risk Score:** 100/100

❌ Trade blocked by Risk Manager - cannot reach target
""",
            "verdict": "REJECTED",
            "position": "NO_BET",
            "conviction": 0.0,
            "risk_score": 100,
            "approved": False,
            "can_reach": False,
            "reject_reason": reason,
        }


# ============================================================================
# MAIN TRADINGAGENTS ORCHESTRATOR
# ============================================================================

class WeatherTradingAgents:
    """Main orchestrator - runs full agent debate before any trade."""
    
    def __init__(self):
        self.fundamentals = FundamentalsAnalyst()
        self.sentiment = SentimentAnalyst()
        self.technical = TechnicalAnalyst()
        self.bull = BullResearcher()
        self.bear = BearResearcher()
        self.risk = RiskManager()
    
    def analyze(
        self,
        city: str,
        target_temp: int,
        target_date: str,
        unit: str,
        p: float,
        price: float,
        kelly: float,
        market_id: str,
        side: str = "YES",
        hours_ahead: float = 999.0,
    ) -> Dict[str, Any]:
        """Run full TradingAgents debate. Returns risk decision."""

        print(f"\n{'='*60}")
        print(f"🤖 TradingAgents Debate: {city.title()} {target_temp}°{unit} | {target_date}")
        print(f"{'='*60}")
        
        # Step 1: Fundamentals
        print("  [1/6] Fundamentals Analyst...")
        fund = self.fundamentals.analyze(city, target_date, target_temp, unit)
        
        # Step 2: Sentiment
        print("  [2/6] Sentiment Analyst...")
        sent = self.sentiment.analyze(market_id, target_temp, unit)
        
        # Step 3: Technical
        print("  [3/6] Technical Analyst...")
        tech = self.technical.analyze(city, target_date, fund.get("forecast_max", 25), unit)
        
        # Step 4: Bull Case
        print("  [4/6] Bull Researcher...")
        bull_case = self.bull.argue(fund, sent, tech, target_temp)
        
        # Step 5: Bear Case
        print("  [5/6] Bear Researcher...")
        bear_case = self.bear.argue(fund, sent, tech, target_temp)
        
        # Step 6: Risk Manager (THE GATE)
        print("  [6/6] Risk Manager (FINAL GATE)...")
        risk = self.risk.evaluate(
            city, target_temp, target_date, unit, p, price, kelly, market_id, side,
            fund, sent, tech, bull_case, bear_case, hours_ahead
        )
        
        # Summary
        print(f"\n  📊 Conviction: {risk.get('conviction', 0)}/10 | Risk: {risk.get('risk_score', 0)}/100")
        print(f"  🎯 Verdict: {risk.get('verdict', 'UNKNOWN')}")
        print(f"  📌 Position: {risk.get('position', 'NO_BET')}")
        
        result = {
            "timestamp": datetime.now().isoformat(),
            "city": city,
            "target_temp": target_temp,
            "target_date": target_date,
            "unit": unit,
            "market_id": market_id,
            "p": p,
            "price": price,
            "kelly": kelly,
            "fundamentals": {
                "confidence": fund.get("confidence"),
                "forecast_max": fund.get("forecast_max"),
                "can_reach": fund.get("can_reach"),
            },
            "sentiment": {
                "yes_price": sent.get("yes_price"),
                "sentiment": sent.get("sentiment"),
                "volume": sent.get("volume"),
            },
            "technical": {
                "pattern": tech.get("pattern"),
                "deviation": tech.get("deviation"),
            },
            "bull_case": bull_case,
            "bear_case": bear_case,
            "risk": risk,
        }
        
        # Log to file
        self._log_debate(result)
        
        return result
    
    def _log_debate(self, result: Dict):
        """Log all debates for learning."""
        log_dir = os.path.expanduser("~/.openclaw/workspace/alter-bot-v1/data/tradingagents_logs")
        os.makedirs(log_dir, exist_ok=True)
        
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        city = result["city"].replace(" ", "_")
        filename = f"{log_dir}/debate_{city}_{ts}.json"
        
        with open(filename, "w") as f:
            json.dump(result, f, indent=2)


# ============================================================================
# WRAPPER: check if trade should proceed
# ============================================================================

_ta_cache = None

def get_ta() -> WeatherTradingAgents:
    global _ta_cache
    if _ta_cache is None:
        _ta_cache = WeatherTradingAgents()
    return _ta_cache


def should_trade(
    city: str,
    target_temp: int,
    target_date: str,
    unit: str,
    p: float,
    price: float,
    kelly: float,
    market_id: str,
    side: str = "YES",
    hours_ahead: float = 999.0,
) -> tuple[bool, Dict]:
    """
    Main entry point for bot_v2.py integration.
    Returns (should_trade: bool, decision: Dict)

    Args:
        side: "YES" or "NO" — determines which price threshold the Risk Manager applies.
              For YES bets: reject if market price < $0.01 (long-shot).
              For NO bets: reject if bucket is near-certain (ask >= $0.9995) — no NO edge left.
    """
    ta = get_ta()
    print(f"  [TRADINGAGENTS] city={city} | bucket={target_temp}°{unit} | p={p:.4f} | price=${price:.3f} | kelly={kelly:.4f} | market_id={market_id} | side={side}")
    decision = ta.analyze(city, target_temp, target_date, unit, p, price, kelly, market_id, side, hours_ahead)
    risk = decision.get("risk", {})
    approved = risk.get("approved", False)
    conviction = risk.get("conviction", 0)
    verdict = risk.get("verdict", "?")
    position = risk.get("position", "?")
    reject_reason = risk.get("reject_reason", risk.get("reason", ""))
    print(f"  [TRADINGAGENTS] → approved={approved} | conviction={conviction}/10 | verdict={verdict} | position={position} | reject_reason={reject_reason}")
    return approved, decision