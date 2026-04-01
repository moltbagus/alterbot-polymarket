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
import requests
from datetime import datetime, timedelta
from typing import Dict, Any, Optional

# Add TradingAgents to path
TA_PATH = os.path.expanduser("~/.openclaw/workspace/TradingAgents")
if os.path.exists(TA_PATH):
    sys.path.insert(0, TA_PATH)

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
        
        current_temp = metar.get("temp", 0) or 0
        forecast_max = forecast.get("max", 0) or 0
        
        # Check if forecast can reach target
        can_reach = forecast_max >= target_temp
        
        # Confidence from forecast gap
        gap = forecast_max - current_temp
        conf = 50
        if can_reach:
            conf += 20
            if forecast_max - target_temp >= 2:
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
    
    def __init__(self):
        self.name = "Technical Analyst (Historical)"
    
    def analyze(self, city: str, target_date: str, forecast_max: float, unit: str = "C") -> Dict[str, Any]:
        # Historical averages by city/month
        HISTORICAL = {
            "singapore": {3: 30, 4: 31, 5: 31, 6: 30, 7: 30, 8: 30, 9: 30, 10: 30, 11: 30, 12: 29},
            "tokyo": {3: 14, 4: 18, 5: 23, 6: 26, 7: 30, 8: 31, 9: 27, 10: 22, 11: 16, 12: 11},
            "seoul": {3: 11, 4: 16, 5: 21, 6: 25, 7: 28, 8: 29, 9: 25, 10: 18, 11: 10, 12: 3},
            "london": {3: 11, 4: 14, 5: 18, 6: 21, 7: 24, 8: 23, 9: 20, 10: 15, 11: 11, 12: 8},
            "nyc": {3: 10, 4: 16, 5: 21, 6: 26, 7: 29, 8: 28, 9: 24, 10: 17, 11: 11, 12: 5},
            "chicago": {3: 8, 4: 14, 5: 20, 6: 25, 7: 28, 8: 27, 9: 23, 10: 15, 11: 8, 12: 1},
            "miami": {3: 26, 4: 28, 5: 30, 6: 31, 7: 32, 8: 32, 9: 31, 10: 29, 11: 26, 12: 24},
        }
        
        target_dt = datetime.strptime(target_date, "%Y-%m-%d")
        month = target_dt.month
        
        hist = HISTORICAL.get(city.lower(), {}).get(month, 25)
        deviation = forecast_max - hist
        
        if deviation > 3:
            pattern = "WARM_ANOMALY"
        elif deviation < -3:
            pattern = "COLD_ANOMALY"
        else:
            pattern = "NORMAL"
        
        report = f"""# Technical Analysis - {city.title()}

## Historical Pattern (Month {month})
- **Historical Avg:** {hist}°{unit}
- **Current Forecast:** {forecast_max}°{unit}
- **Deviation:** {deviation:+.1f}°{unit}

## Pattern: {pattern}
{'Above normal temperatures - favorable for reaching high targets' if deviation > 0 else 'Below normal - headwind for warm targets' if deviation < -2 else 'Near normal conditions'}

## Signal
{pattern}
"""
        return {
            "report": report,
            "historical_avg": hist,
            "deviation": deviation,
            "pattern": pattern,
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
        self.min_conviction = 7  # Must score >= 7/10 to approve
        self.max_risk_score = 60  # Risk score must be <= 60/100
    
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
        fundamentals: Dict,
        sentiment: Dict,
        technical: Dict,
        bull_case: str,
        bear_case: str,
    ) -> Dict[str, Any]:
        
        sentiment_data = get_polymarket_odds(market_id) if market_id else {}
        
        # Calculate conviction score (0-10)
        conviction = 5  # Start neutral
        
        # Factor 1: Can forecast reach target?
        if not fundamentals.get("can_reach", True):
            return self._rejected(
                city, target_temp, target_date, unit, p, price,
                "REJECTED: Forecast cannot reach target temperature. Mathematically impossible to resolve YES.",
                fundamentals, sentiment, technical, bull_case, bear_case
            )
        conviction += 1
        
        # Factor 2: Fundamentals confidence
        conf = fundamentals.get("confidence", 50)
        if conf >= 75:
            conviction += 1.5
        elif conf >= 60:
            conviction += 1
        elif conf < 40:
            conviction -= 1
        
        # Factor 3: Market alignment
        yes_price = sentiment.get("yes_price", 0.5) or sentiment_data.get("yes_price", 0.5)
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
            "factors": {
                "fundamentals_confidence": conf,
                "yes_price": yes_price,
                "technical_pattern": technical.get("pattern", "NORMAL"),
                "kelly": kelly,
                "ev": round(ev, 3),
            }
        }
    
    def _get_position(self, kelly: float, conviction: float) -> str:
        if conviction >= 9:
            return "MAX_BET"
        elif conviction >= 8:
            return "STANDARD_BET"
        elif conviction >= 7:
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
            city, target_temp, target_date, unit, p, price, kelly, market_id,
            fund, sent, tech, bull_case, bear_case
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
) -> tuple[bool, Dict]:
    """
    Main entry point for bot_v2.py integration.
    Returns (should_trade: bool, decision: Dict)
    """
    ta = get_ta()
    decision = ta.analyze(city, target_temp, target_date, unit, p, price, kelly, market_id)
    
    approved = decision.get("risk", {}).get("approved", False)
    return approved, decision