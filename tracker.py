#!/usr/bin/env python3
"""
Polymarket Temperature Bet Tracker v3
- Fetches live METAR for all cities (uses correct resolution station ICAOs)
- Pulls Open-Meteo 7-day forecast for each city
- Estimates peak temp using calibrated model (OM forecast + METAR offset)
- Accounts for Wunderground rounding to WHOLE DEGREES
- Scans Polymarket April 4 and April 5 temperature markets
- Filters for EV >= 15%, price >= 3%, volume >= $2K
- Logs to ~/polymarket-tracker.log
Usage: python3 ~/polymarket-tracker.py [4|5|both]

Key fixes v3:
- Seoul ICAO: RKSI (Incheon) not RKSS (Gimpo) — market resolves at Incheon
- Rounding model: p_round_to() for "be N°C" markets, p_above()/p_below() for thresholds
- This matches Wunderground's whole-degree rounding behavior
"""

import urllib.request, urllib.parse, json, math, time, os, socket
from datetime import datetime, timezone

GAMMA = 'https://gamma-api.polymarket.com'
METEO = 'https://aviationweather.gov/api/data/metar'
OPENMETEO = 'https://api.open-meteo.com/v1/forecast'
MAX_STAKE = 5.0
MIN_PRICE = 0.03
MIN_VOL = 2000  # $2K minimum market volume

def _get(url, delay=0.3):
    req = urllib.request.Request(url, headers={'User-Agent': 'hermes-agent/1.0'})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read().decode())
    time.sleep(delay)

def parse_json(v):
    if isinstance(v, str):
        try: return json.loads(v)
        except: return v
    return v

def norm_cdf(x):
    a1,a2,a3,a4,a5=0.254829592,-0.284496736,1.421413741,-1.453152027,1.061405429; p=0.3275911
    sign=-1 if x<0 else 1; x=abs(x)/math.sqrt(2); t=1.0/(1.0+p*x)
    y=1.0-(((((a5*t+a4)*t+a3)*t+a2)*t+a1)*t)*math.exp(-x*x)
    return 0.5*(1.0+sign*y)

def bp(f, lo, hi, s):
    """Old continuous bucket probability — use p_round_to / p_above / p_below instead."""
    if lo==-999: return norm_cdf((hi-f)/s)
    if hi==999: return 1.0-norm_cdf((lo-f)/s)
    return max(0.0, min(1.0, norm_cdf((hi-f)/s)-norm_cdf((lo-f)/s)))

def p_round_to(target, peak, sigma):
    """P(peak rounds to target whole degree per Wunderground rounding)."""
    lo = target - 0.5
    hi = target + 0.5
    return max(0.0, min(1.0,
        norm_cdf((hi - peak) / sigma) - norm_cdf((lo - peak) / sigma)))

def p_above(target, peak, sigma):
    """P(peak >= target) accounting for whole-degree rounding."""
    return 1.0 - norm_cdf((target - 0.5 - peak) / sigma)

def p_below(target, peak, sigma):
    """P(peak <= target) accounting for whole-degree rounding."""
    return norm_cdf((target + 0.5 - peak) / sigma)

def ev(p, pr):
    if pr<=0 or pr>=1: return 0.0
    return round(p*(1.0/pr-1)-(1.0-p), 4)

def kelly(bal, p, pr, kf=0.2):
    if pr<=0 or pr>=1: return 0.0
    b=(1.0/pr)-1.0; q=1.0-p; kel=(b*p-q)/b
    if kel<=0: return 0.0
    return min(kel*kf*bal, bal*0.10, MAX_STAKE)

def xb(q):
    """Parse question into bucket bounds + type.
    Returns (lo, hi, qtype) where qtype is 'exact', 'above', or 'below'."""
    import re; q=q.lower()
    m=re.search(r'be\s+(\d+)\s*°?c',q)
    if m:
        t=int(m.group(1))
        return(t-0.5, t+0.5, 'exact')
    m=re.search(r'(\d+)\s*°?c\s+or\s+below',q)
    if m:
        return(-999, int(m.group(1))+0.5, 'below')
    m=re.search(r'(\d+)\s*°?c\s+or\s+(above|higher)',q)
    if m:
        return(int(m.group(1))-0.5, 999, 'above')
    return(None, None, None)

fp=lambda p: f'{float(p)*100:.1f}%'
fe=lambda e: f'{e*100:+.1f}%'

# === CITY CONFIGS ===
# lat/lon for Open-Meteo, ICAO for METAR, tz offset from UTC
CITIES = [
    {'name':'Tokyo',        'icao':'RJTT', 'lat':35.5,   'lon':139.7,   'tz':9,  'sigma':0.5},
    {'name':'Singapore',    'icao':'WSSS', 'lat':1.35,   'lon':103.9,   'tz':8,  'sigma':0.4},
    {'name':'London',        'icao':'EGLL', 'lat':51.5,   'lon':-0.5,    'tz':1,  'sigma':0.7},
    {'name':'Paris',         'icao':'LFPO', 'lat':49.0,   'lon':2.5,     'tz':2,  'sigma':0.6},
    {'name':'Seoul',         'icao':'RKSI', 'lat':37.5,   'lon':126.9,   'tz':9,  'sigma':0.5},
    {'name':'Shanghai',      'icao':'ZSPD', 'lat':31.2,   'lon':121.5,   'tz':8,  'sigma':0.6},
    {'name':'Beijing',       'icao':'ZBAA', 'lat':40.1,   'lon':116.6,   'tz':8,  'sigma':0.6},
    {'name':'Wellington',    'icao':'NZWN', 'lat':-41.3,  'lon':174.8,   'tz':12, 'sigma':0.5},
    {'name':'Amsterdam',     'icao':'EHAM', 'lat':52.3,   'lon':4.8,     'tz':2,  'sigma':0.6},
    {'name':'Toronto',       'icao':'CYYZ', 'lat':43.7,   'lon':-79.6,   'tz':-4, 'sigma':0.7},
    {'name':'New York',      'icao':'KJFK', 'lat':40.6,   'lon':-73.8,   'tz':-4, 'sigma':0.7},
    {'name':'Chicago',       'icao':'KORD', 'lat':42.0,   'lon':-87.9,   'tz':-5, 'sigma':0.7},
    {'name':'Buenos Aires',  'icao':'SAEZ', 'lat':-34.8,  'lon':-58.5,   'tz':-3, 'sigma':0.6},
]

# Map Open-Meteo weather codes to human-readable
WX_MAP = {
    0:'Clear',1:'Mainly clear',2:'Partly cloudy',3:'Overcast',
    45:'Fog',48:'Rime fog',51:'Light drizzle',53:'Drizzle',
    55:'Heavy drizzle',61:'Light rain',63:'Rain',65:'Heavy rain',
    71:'Light snow',73:'Snow',75:'Heavy snow',80:'Rain showers',
    81:'Rain showers',82:'Violent showers',95:'Thunderstorm',
    96:'Thunderstorm',99:'Thunderstorm'
}

def get_open_meteo_forecast(lat, lon, tz_name, target_date):
    """Fetch Open-Meteo hourly forecast for a specific date."""
    url = (f'{OPENMETEO}?latitude={lat}&longitude={lon}'
           f'&daily=temperature_2m_max,temperature_2m_min,weathercode,precipitation_sum,windspeed_10m_max'
           f'&hourly=temperature_2m,weathercode,windspeed_10m'
           f'&timezone={urllib.parse.quote(tz_name)}&forecast_days=7')
    try:
        d = _get(url)
    except Exception as e:
        return None, str(e)
    
    daily = d.get('daily', {})
    hourly = d.get('hourly', {})
    
    # Find the target date index in daily
    dates = daily.get('time', [])
    if target_date not in dates:
        return None, f'Date {target_date} not in forecast'
    
    idx = dates.index(target_date)
    
    # Daily summary
    om_max = daily['temperature_2m_max'][idx]
    om_min = daily['temperature_2m_min'][idx]
    wx_code = daily['weathercode'][idx]
    wx = WX_MAP.get(wx_code, f'code={wx_code}')
    wind_max = daily['windspeed_10m_max'][idx]
    precip = daily['precipitation_sum'][idx]
    
    # Hourly breakdown for target date
    hourly_times = hourly.get('time', [])
    hourly_temps = hourly.get('temperature_2m', [])
    hourly_codes = hourly.get('weathercode', [])
    
    day_hours = []
    for j in range(len(hourly_times)):
        if hourly_times[j].startswith(target_date):
            t = float(hourly_temps[j])
            c = hourly_codes[j]
            day_hours.append({'time': hourly_times[j], 'temp': t, 'wx': WX_MAP.get(c, f'code={c}')})
    
    if day_hours:
        peak = max(h['temp'] for h in day_hours)
        min_t = min(h['temp'] for h in day_hours)
        peak_time = [h['time'] for h in day_hours if h['temp']==peak][0]
    else:
        peak = om_max
        min_t = om_min
        peak_time = target_date + 'T12:00'
    
    return {
        'om_max': float(om_max), 'om_min': float(om_min),
        'peak': peak, 'min_temp': min_t, 'peak_time': peak_time,
        'wx': wx, 'wind_max': wind_max, 'precip': precip,
        'day_hours': day_hours, 'idx': idx
    }, ''

def estimate_peak_with_om(om_data, metar_temp, local_hour):
    """
    Estimate peak temp using:
    1. Open-Meteo raw forecast peak for that day
    2. Calibration offset (how much METAR differs from OM at current hour)
    3. Time-of-day adjustment
    """
    if om_data is None:
        # Fallback: rough diurnal estimate
        return metar_temp + 3.0, 'No forecast'
    
    om_peak = om_data['peak']
    om_min = om_data['min_temp']
    day_hours = om_data['day_hours']
    
    # If we have current hour data, compute calibration offset
    if day_hours:
        # Find the OM forecast temp at the current local hour
        # hourly times are in UTC, local hour is already computed
        hour_idx = local_hour
        if hour_idx < len(day_hours):
            om_current = day_hours[hour_idx]['temp']
        else:
            om_current = day_hours[-1]['temp']
        
        if metar_temp is not None:
            offset = metar_temp - om_current
        else:
            offset = 0.0
        
        # Calibrated peak
        calibrated_peak = round(om_peak + offset, 1)
        
        # Additional adjustment: if we're near/at peak time, don't over-adjust
        # Peak time is typically 13-15 local
        hours_to_peak = 14 - local_hour if local_hour < 14 else 0
        if hours_to_peak > 0 and abs(offset) > 2:
            # Big discrepancy — don't trust it blindly, blend toward OM
            calibrated_peak = round(om_peak + offset * 0.5, 1)
        
        return calibrated_peak, f'OM={om_peak}C offset={offset:+.1f}C'
    
    return om_peak, f'OM={om_peak}C (no hourly)'

def get_metar(icao):
    """Fetch METAR for an ICAO station."""
    try:
        req = urllib.request.Request(
            f'{METEO}?ids={icao}&format=json',
            headers={'User-Agent': 'hermes-agent/1.0'}
        )
        with urllib.request.urlopen(req, timeout=10) as r:
            m = json.loads(r.read().decode())[0]
        return {
            'temp': m.get('temp'),
            'wind_dir': m.get('wdir'),
            'wind_spd': m.get('wspd'),
            'wx': m.get('wxString', ''),
            'cover': m.get('cover', ''),
            'utc': m.get('reportTime', '')[:16]
        }, ''
    except Exception as e:
        return None, str(e)

def get_tz_name(city_name):
    """Map city name to Open-Meteo timezone string."""
    tz_map = {
        'Tokyo': 'Asia/Tokyo', 'Singapore': 'Asia/Singapore',
        'London': 'Europe/London', 'Paris': 'Europe/Paris',
        'Seoul': 'Asia/Seoul', 'Shanghai': 'Asia/Shanghai',
        'Beijing': 'Asia/Shanghai', 'Wellington': 'Pacific/Auckland',
        'Amsterdam': 'Europe/Amsterdam', 'Toronto': 'America/Toronto',
        'New York': 'America/New_York', 'Chicago': 'America/Chicago',
        'Buenos Aires': 'America/Buenos_Aires'
    }
    return tz_map.get(city_name, 'UTC')

def analyze_city(city, target_date):
    """Analyze a single city for a specific date."""
    name = city['name']
    icao = city['icao']
    lat, lon = city['lat'], city['lon']
    tz_offset = city['tz']
    sigma = city['sigma']
    
    # Fetch METAR
    metar, merr = get_metar(icao)
    if merr:
        return None, f'METAR error: {merr}'
    
    temp_c = metar['temp']
    wind = f'{metar["wind_dir"]}deg/{metar["wind_spd"]}kt'
    wx = metar['wx'] or metar['cover'] or 'clear'
    report_utc = metar['utc']
    
    # Calculate local hour
    try:
        utc_dt = datetime.strptime(report_utc, '%Y-%m-%dT%H:%M')
        local_hour = (utc_dt.hour + tz_offset) % 24
    except:
        local_hour = 12
    
    # Get Open-Meteo forecast
    tz_name = get_tz_name(name)
    date_str = f'2026-04-{int(target_date):02d}'
    om, om_err = get_open_meteo_forecast(lat, lon, tz_name, date_str)
    
    if om_err:
        peak, note = estimate_peak_with_om(None, temp_c, local_hour)
        om_peak = None
    else:
        om_peak = om.get('om_max')
        peak, note = estimate_peak_with_om(om, temp_c, local_hour)
    
    # Fetch market
    slug = f'highest-temperature-in-{name.lower().replace(" ","-")}-on-april-{target_date}-2026'
    evts = _get(f'{GAMMA}/events?slug={urllib.parse.quote(slug)}')
    
    if not evts:
        return None, f'No event found for Apr {target_date}'
    
    evt = evts[0]
    markets = evt.get('markets', [])
    
    opps = []
    for mx in markets:
        if mx.get('closed'): continue
        prices = parse_json(mx.get('outcomePrices', '[]'))
        if not isinstance(prices, list) or len(prices) < 2: continue
        mkt_vol = float(mx.get('volume', 0))
        if mkt_vol < MIN_VOL: continue
        
        q = mx['question']
        t_low, t_high, qtype = xb(q)
        if t_low is None: continue
        
        mkt = float(prices[0])
        if mkt < MIN_PRICE: continue
        
        # Use rounding-aware probability based on question type
        if qtype == 'exact':
            target = int(round((t_low + t_high) / 2))
            mp = p_round_to(target, peak, sigma)
        elif qtype == 'above':
            mp = p_above(int(round(t_low + 0.5)), peak, sigma)
        else:  # 'below'
            mp = p_below(int(round(t_high - 0.5)), peak, sigma)
        
        ev_yes = ev(mp, mkt)
        ev_no = ev(1-mp, 1-mkt)
        best = max(ev_yes, ev_no)
        direction = 'YES' if ev_yes >= ev_no else 'NO'
        
        if best >= 0.15:
            ap = mp if direction=='YES' else 1-mp
            pr = mkt if direction=='YES' else 1-mkt
            k = kelly(100, ap, pr)
            opps.append({
                'q': q[:60], 'dir': direction, 'mkt': mkt,
                'model': ap, 'ev': best, 'kelly': k,
                'vol': mkt_vol, 't_low': t_low, 't_high': t_high
            })
    
    opps.sort(key=lambda x: -x['ev'])
    
    return {
        'city': name, 'temp': temp_c, 'peak': peak,
        'om_peak': om_peak, 'sigma': sigma,
        'wind': wind, 'wx': wx, 'report': report_utc,
        'local_hour': local_hour, 'note': note,
        'target_date': target_date,
        'om_data': om,
        'opps': opps[:5]
    }, ''

def build_report(target_dates):
    lines = []
    now = datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')
    
    if target_dates == ['both']:
        dates = ['4', '5']
        title = f'APRIL 4 + 5 — {now}'
    else:
        dates = target_dates
        title = f'APRIL {dates[0]} — {now}'
    
    lines.append('='*60)
    lines.append(f'POLYMARKET TEMP TRACKER v2 — {title}')
    lines.append('='*60)
    lines.append('')
    
    all_opps = []
    
    for date in dates:
        lines.append(f'--- APRIL {date} ---')
        lines.append('')
        
        for city in CITIES:
            data, err = analyze_city(city, date)
            
            if err or data is None or 'city' not in data:
                lines.append(f'  {city["name"]}: {err or "no data"}')
                continue
            
            peak = data['peak']
            temp = data['temp']
            om_peak = data.get('om_peak')
            tz = city['tz']
            local_time = data['report']
            lh = data['local_hour']
            
            lines.append(f'{data["city"].upper()}')
            lines.append(f'  METAR: {temp}C ({lh:02d}:00 local) | Peak: {peak}C')
            if om_peak:
                lines.append(f'  Open-Meteo: {om_peak}C | {data["wx"]} | Wind max: {data["wind"]}')
            else:
                lines.append(f'  Wind: {data["wind"]} | Wx: {data["wx"]}')
            lines.append(f'  [{data["note"]}]')
            
            if data.get('om_data'):
                om = data['om_data']
                wx = om.get('wx', '')
                precip = om.get('precip', 0)
                if precip:
                    lines.append(f'  Forecast: {wx} | precip={precip}mm')
                else:
                    lines.append(f'  Forecast: {wx}')
            
            if data['opps']:
                lines.append('  Opportunities:')
                for o in data['opps'][:3]:
                    flag = ' ★' if o['ev'] >= 0.50 else ''
                    lines.append(f'    [{o["dir"]}] {o["q"][:55]}')
                    lines.append(f'      Price: {fp(o["mkt"])} | Model: {fp(o["model"])} | EV: {fe(o["ev"])} | Kelly: ${o["kelly"]:.1f}{flag}')
                    all_opps.append({**o, 'city': data['city'], 'date': date, 'peak': peak})
            else:
                lines.append('  No high-EV opportunities')
            
            lines.append('')
    
    # Summary
    if all_opps:
        lines.append('='*60)
        lines.append('TOP BETS ACROSS ALL CITIES')
        lines.append('='*60)
        all_opps.sort(key=lambda x: -x['ev'])
        for i, o in enumerate(all_opps[:10], 1):
            flag = ' ★★' if o['ev'] >= 0.50 else '  '
            lines.append(f'{i}. {o["city"]} Apr {o["date"]}: {o["q"][:55]}{flag}')
            lines.append(f'   Peak: {o["peak"]}C | [{o["dir"]}] {fp(o["mkt"])} | Model: {fp(o["model"])} | EV: {fe(o["ev"])} | Kelly: ${o["kelly"]:.1f}')
    else:
        lines.append('No actionable bets found at this time.')
    
    return '\n'.join(lines)

if __name__ == '__main__':
    import sys
    arg = sys.argv[1] if len(sys.argv) > 1 else '4'
    
    if arg == 'both':
        dates = ['both']
    elif arg == '4':
        dates = ['4']
    elif arg == '5':
        dates = ['5']
    else:
        dates = [arg]
    
    report = build_report(dates)
    print(report)
    
    # Save log
    log_path = os.path.expanduser('~/polymarket-tracker.log')
    hostname = socket.gethostname()
    ts = datetime.now(timezone.utc).isoformat()
    
    with open(log_path, 'a') as f:
        f.write(f'\n--- Run at {ts} on {hostname} ---\n')
        f.write(report + '\n')
    
    print(f'\n[Saved to {log_path}]')
