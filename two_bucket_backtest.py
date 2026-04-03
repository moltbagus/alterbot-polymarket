#!/usr/bin/env python3
"""
2-Bucket Adjacent Betting Strategy Backtest
Compares single bucket vs betting on 2 adjacent buckets.

Key insight: When our prediction is off by 1 bucket, do we still profit
by hedging with an adjacent bucket bet?
"""

import json
import math
import glob
import os
from collections import defaultdict
from datetime import datetime

DATA_DIR = '/home/alyssa/.openclaw/workspace/alter-bot-v1/data'

def estimate_bucket_probs_normal(predicted_temp, sigma=1.08, bucket_size=1.0):
    """
    Estimate Polymarket bucket probabilities using normal distribution.
    Price of bucket = probability that actual temp falls in that bucket.
    """
    probs = {}
    
    for offset in range(-4, 5):  # -4 to +4 buckets
        bucket_temp = round(predicted_temp + offset * bucket_size)
        lower = bucket_temp - 0.5
        upper = bucket_temp + 0.5
        
        # CDF approach for P(lower < X < upper)
        cdf_upper = 0.5 * (1 + math.erf((upper - predicted_temp) / (sigma * math.sqrt(2))))
        cdf_lower = 0.5 * (1 + math.erf((lower - predicted_temp) / (sigma * math.sqrt(2))))
        prob = max(0, cdf_upper - cdf_lower)
        probs[bucket_temp] = prob
    
    # Normalize so sum = 1
    total = sum(probs.values())
    if total > 0:
        probs = {k: v/total for k, v in probs.items()}
    
    return probs

def estimate_bucket_price(predicted_temp, bucket_temp, sigma=1.08):
    """
    Estimate the Polymarket YES price for a specific bucket.
    Price = P(actual temp in bucket) using normal distribution.
    Clipped to [0.05, 0.90] for realistic Polymarket pricing.
    """
    lower = bucket_temp - 0.5
    upper = bucket_temp + 0.5
    
    cdf_upper = 0.5 * (1 + math.erf((upper - predicted_temp) / (sigma * math.sqrt(2))))
    cdf_lower = 0.5 * (1 + math.erf((lower - predicted_temp) / (sigma * math.sqrt(2))))
    prob = max(0, cdf_upper - cdf_lower)
    
    return min(0.90, max(0.05, prob))

def parse_bucket_temp(bucket_str):
    """Parse bucket string like '28' or '26-30' or '32 or higher' to center temp."""
    if not bucket_str:
        return None
    s = str(bucket_str).replace('\u00b0C', '').replace('C', '').strip()
    
    if 'or below' in bucket_str.lower():
        # "26 or below" -> the bucket is at 26
        try:
            return float(s.split()[0])
        except:
            return None
    elif 'or higher' in bucket_str.lower():
        try:
            return float(s.split()[0])
        except:
            return None
    elif '-' in s:
        parts = s.split('-')
        try:
            return (float(parts[0]) + float(parts[1])) / 2
        except:
            return None
    else:
        try:
            return float(s)
        except:
            return None

def load_asian_cities_predictions():
    """Load predictions from asian_cities_daily_backtest.json"""
    print("\n=== Loading asian_cities_daily_backtest.json ===")
    with open(f'{DATA_DIR}/asian_cities_daily_backtest.json') as f:
        data = json.load(f)
    
    trades = []
    for city, city_data in data.items():
        mae = city_data.get('default_metrics', {}).get('mae', 1.08)
        for p in city_data.get('predictions', []):
            if p.get('actual') is None:
                continue
            
            pred_temp = float(p['predicted'])
            actual_temp = float(p['actual'])
            
            # Parse buckets
            pred_bucket = parse_bucket_temp(p.get('bucket'))
            actual_bucket = parse_bucket_temp(p.get('actual_bucket'))
            
            if pred_bucket is None or actual_bucket is None:
                continue
            
            trades.append({
                'city': city,
                'date': p['date'],
                'pred_temp': pred_temp,
                'actual_temp': actual_temp,
                'pred_bucket': int(pred_bucket),
                'actual_bucket': int(actual_bucket),
                'mae': mae,
                'bucket_win': p.get('bucket_win', pred_bucket == int(actual_bucket))
            })
    
    print(f"Loaded {len(trades)} trades (asian_cities)")
    return trades

def load_browser_polymarket():
    """Load predictions from browser_polymarket_backtest.json"""
    print("\n=== Loading browser_polymarket_backtest.json ===")
    with open(f'{DATA_DIR}/browser_polymarket_backtest.json') as f:
        data = json.load(f)
    
    trades = []
    for item in data.get('data', []):
        pred = float(item['pred'])
        actual = float(item['actual'])
        
        trades.append({
            'city': item['city'],
            'date': item['date'],
            'pred_temp': pred,
            'actual_temp': actual,
            'pred_bucket': int(pred),
            'actual_bucket': int(pred) if actual == pred else int(actual),
            'bucket_win': item['correct']
        })
    
    print(f"Loaded {len(trades)} trades (browser_polymarket)")
    return trades

def load_beijing_backtest():
    """Load beijing backtest with known outcomes"""
    print("\n=== Loading beijing_daily_backtest.json ===")
    with open(f'{DATA_DIR}/beijing_daily_backtest.json') as f:
        data = json.load(f)
    
    trades = []
    for p in data['daily_backtest'].get('sample_predictions', []):
        pred_bucket = parse_bucket_temp(p.get('predicted_bucket'))
        actual_bucket = parse_bucket_temp(p.get('actual_bucket'))
        actual_high = p.get('actual_high')
        
        if pred_bucket is None or actual_bucket is None:
            continue
        
        trades.append({
            'city': 'beijing',
            'date': p['date'],
            'pred_temp': pred_bucket,  # bucket is the pred
            'actual_temp': actual_high,
            'pred_bucket': int(pred_bucket),
            'actual_bucket': int(actual_bucket),
            'bucket_win': p.get('won', pred_bucket == actual_bucket)
        })
    
    print(f"Loaded {len(trades)} trades (beijing)")
    return trades

def calculate_pnl(bet_amount, price, won):
    """
    Calculate P&L for a binary option bet.
    If won: bet_amount * (1-price)/price (profit on the bet)
    If lost: -bet_amount (lose the stake)
    """
    if won:
        return bet_amount * (1 - price) / price
    else:
        return -bet_amount

def run_backtest():
    print("=" * 65)
    print("  2-BUCKET ADJACENT BETTING STRATEGY BACKTEST")
    print("=" * 65)
    print(f"Started: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    
    # Load all data
    all_trades = []
    all_trades.extend(load_asian_cities_predictions())
    all_trades.extend(load_browser_polymarket())
    all_trades.extend(load_beijing_backtest())
    
    # Deduplicate by city+date
    seen = set()
    unique_trades = []
    for t in all_trades:
        key = (t['city'].lower(), t['date'])
        if key not in seen:
            seen.add(key)
            unique_trades.append(t)
    
    trades = unique_trades
    print(f"\nTotal unique trades for analysis: {len(trades)}")
    
    # Strategy parameters
    SIGMA = 1.08  # Use 1.08°C as default sigma (MAE from data)
    BUCKET_SIZE = 1.0
    BET_SIZE = 1.0  # $1 total per trade for single bucket
    TWO_BUCKET_SIZE = 0.50  # $0.50 per bucket in 2-bucket strategy
    
    # Results tracking
    # Strategy 1: Single bucket - bet $1 on predicted bucket
    s1_wins = 0
    s1_losses = 0
    s1_profit = 0.0
    s1_trades = []
    
    # Strategy 2: 2-bucket below - bet $0.50 on predicted + $0.50 on bucket-1
    s2_wins = 0
    s2_losses = 0
    s2_profit = 0.0
    s2_trades = []
    
    # Strategy 3: 2-bucket above - bet $0.50 on predicted + $0.50 on bucket+1
    s3_wins = 0
    s3_losses = 0
    s3_profit = 0.0
    s3_trades = []
    
    # Strategy 4: 2-bucket both sides - bet $0.33 on predicted + $0.33 on bucket-1 + $0.33 on bucket+1
    s4_wins = 0
    s4_losses = 0
    s4_profit = 0.0
    s4_trades = []
    
    # Adjacent bucket accuracy stats
    adj_below_wins = 0  # would have won if we'd bet on bucket-1
    adj_above_wins = 0  # would have won if we'd bet on bucket+1
    
    print(f"\nRunning analysis with sigma={SIGMA:.2f}°C...")
    print("-" * 65)
    
    for i, trade in enumerate(trades):
        if i > 0 and i % 20 == 0:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] Processed {i}/{len(trades)} trades...")
        
        pred_temp = trade['pred_temp']
        actual_temp = trade['actual_temp']
        pred_bucket = trade['pred_bucket']
        actual_bucket = trade['actual_bucket']
        city = trade['city']
        date = trade['date']
        
        # Use city-specific sigma if available
        sigma = trade.get('mae', SIGMA)
        
        # Get estimated prices
        pred_price = estimate_bucket_price(pred_temp, pred_bucket, sigma)
        
        # Adjacent buckets
        adj_below = pred_bucket - 1
        adj_above = pred_bucket + 1
        adj_below_price = estimate_bucket_price(pred_temp, adj_below, sigma)
        adj_above_price = estimate_bucket_price(pred_temp, adj_above, sigma)
        
        # === STRATEGY 1: Single bucket ===
        s1_win = (actual_bucket == pred_bucket)
        s1_pnl = calculate_pnl(BET_SIZE, pred_price, s1_win)
        s1_wins += 1 if s1_win else 0
        s1_losses += 0 if s1_win else 1
        s1_profit += s1_pnl
        s1_trades.append({
            'city': city, 'date': date,
            'pred_bucket': pred_bucket, 'actual_bucket': actual_bucket,
            'pred_price': round(pred_price, 3),
            'pnl': round(s1_pnl, 3), 'win': s1_win
        })
        
        # === STRATEGY 2: 2-bucket (predicted + below) ===
        s2_win = (actual_bucket == pred_bucket) or (actual_bucket == adj_below)
        if s2_win:
            if actual_bucket == pred_bucket:
                # Won on predicted, lost on below
                win_pnl = calculate_pnl(TWO_BUCKET_SIZE, pred_price, True)
                lose_pnl = calculate_pnl(TWO_BUCKET_SIZE, adj_below_price, False)
                s2_pnl = win_pnl + lose_pnl
            else:
                # Won on below, lost on predicted
                win_pnl = calculate_pnl(TWO_BUCKET_SIZE, adj_below_price, True)
                lose_pnl = calculate_pnl(TWO_BUCKET_SIZE, pred_price, False)
                s2_pnl = win_pnl + lose_pnl
        else:
            s2_pnl = -BET_SIZE  # lost both
        
        s2_wins += 1 if s2_win else 0
        s2_losses += 0 if s2_win else 1
        s2_profit += s2_pnl
        s2_trades.append({
            'city': city, 'date': date,
            'pred_bucket': pred_bucket, 'adj_bucket': adj_below, 'actual_bucket': actual_bucket,
            'pred_price': round(pred_price, 3), 'adj_price': round(adj_below_price, 3),
            'pnl': round(s2_pnl, 3), 'win': s2_win
        })
        
        # === STRATEGY 3: 2-bucket (predicted + above) ===
        s3_win = (actual_bucket == pred_bucket) or (actual_bucket == adj_above)
        if s3_win:
            if actual_bucket == pred_bucket:
                win_pnl = calculate_pnl(TWO_BUCKET_SIZE, pred_price, True)
                lose_pnl = calculate_pnl(TWO_BUCKET_SIZE, adj_above_price, False)
                s3_pnl = win_pnl + lose_pnl
            else:
                win_pnl = calculate_pnl(TWO_BUCKET_SIZE, adj_above_price, True)
                lose_pnl = calculate_pnl(TWO_BUCKET_SIZE, pred_price, False)
                s3_pnl = win_pnl + lose_pnl
        else:
            s3_pnl = -BET_SIZE
        
        s3_wins += 1 if s3_win else 0
        s3_losses += 0 if s3_win else 1
        s3_profit += s3_pnl
        s3_trades.append({
            'city': city, 'date': date,
            'pred_bucket': pred_bucket, 'adj_bucket': adj_above, 'actual_bucket': actual_bucket,
            'pred_price': round(pred_price, 3), 'adj_price': round(adj_above_price, 3),
            'pnl': round(s3_pnl, 3), 'win': s3_win
        })
        
        # === STRATEGY 4: 3-bucket (predicted + both adjacents) ===
        THREE_SIZE = 0.33  # $0.33 per bucket
        s4_win = (actual_bucket == pred_bucket) or (actual_bucket == adj_below) or (actual_bucket == adj_above)
        if s4_win:
            if actual_bucket == pred_bucket:
                win_pnl = calculate_pnl(THREE_SIZE, pred_price, True)
                lose_pnl = calculate_pnl(THREE_SIZE, adj_below_price, False) + calculate_pnl(THREE_SIZE, adj_above_price, False)
                s4_pnl = win_pnl + lose_pnl
            elif actual_bucket == adj_below:
                win_pnl = calculate_pnl(THREE_SIZE, adj_below_price, True)
                lose_pnl = calculate_pnl(THREE_SIZE, pred_price, False) + calculate_pnl(THREE_SIZE, adj_above_price, False)
                s4_pnl = win_pnl + lose_pnl
            else:  # adj_above
                win_pnl = calculate_pnl(THREE_SIZE, adj_above_price, True)
                lose_pnl = calculate_pnl(THREE_SIZE, pred_price, False) + calculate_pnl(THREE_SIZE, adj_below_price, False)
                s4_pnl = win_pnl + lose_pnl
        else:
            s4_pnl = -BET_SIZE
        
        s4_wins += 1 if s4_win else 0
        s4_losses += 0 if s4_win else 1
        s4_profit += s4_pnl
        s4_trades.append({
            'city': city, 'date': date,
            'pred_bucket': pred_bucket, 'adj_below': adj_below, 'adj_above': adj_above,
            'actual_bucket': actual_bucket,
            'pred_price': round(pred_price, 3),
            'pnl': round(s4_pnl, 3), 'win': s4_win
        })
        
        # Track "would have won" on adjacent only
        if actual_bucket == adj_below:
            adj_below_wins += 1
        if actual_bucket == adj_above:
            adj_above_wins += 1
    
    n = len(trades)
    if n == 0:
        print("ERROR: No trades found!")
        return
    
    # Calculate stats
    strategies = [
        ('SINGLE BUCKET ($1 on predicted)', s1_wins, s1_losses, s1_profit, s1_trades),
        ('2-BUCKET BELOW ($0.50 pred + $0.50 bkt-1)', s2_wins, s2_losses, s2_profit, s2_trades),
        ('2-BUCKET ABOVE ($0.50 pred + $0.50 bkt+1)', s3_wins, s3_losses, s3_profit, s3_trades),
        ('3-BUCKET ($0.33 each on bkt-1,pred,bkt+1)', s4_wins, s4_losses, s4_profit, s4_trades),
    ]
    
    print("\n" + "=" * 65)
    print("  BACKTEST RESULTS")
    print("=" * 65)
    print(f"  Total trades analyzed: {n}")
    print(f"  Sigma used: {SIGMA:.2f}°C (estimated from MAE)")
    print()
    
    print(f"  {'Strategy':<42} {'Win Rate':>8} {'W-L':>10} {'Total P/L':>12}")
    print("  " + "-" * 75)
    
    best_wr = 0
    best_strategy = ""
    best_profit = -999
    
    for name, wins, losses, profit, trades_list in strategies:
        wr = wins / n * 100
        label = f"{wins}-{losses}"
        print(f"  {name:<42} {wr:>7.1f}%  {label:>9}  ${profit:>10.2f}")
        if wr > best_wr:
            best_wr = wr
            best_strategy = name
        if profit > best_profit:
            best_profit = profit
    
    # Detailed single bucket breakdown
    print("\n" + "=" * 65)
    print("  SINGLE BUCKET ANALYSIS")
    print("=" * 65)
    
    # Break down by error distance
    error_distances = defaultdict(lambda: {'wins': 0, 'losses': 0})
    for t in s1_trades:
        dist = abs(t['actual_bucket'] - t['pred_bucket'])
        if t['win']:
            error_distances[dist]['wins'] += 1
        else:
            error_distances[dist]['losses'] += 1
    
    print(f"\n  Error distance analysis:")
    print(f"  {'Distance':<12} {'Wins':>8} {'Losses':>8} {'Win Rate':>10}")
    print("  " + "-" * 42)
    for dist in sorted(error_distances.keys()):
        d = error_distances[dist]
        total = d['wins'] + d['losses']
        wr = d['wins'] / total * 100 if total > 0 else 0
        print(f"  dist={dist:+3d}:   {d['wins']:>6} wins  {d['losses']:>6} losses  {wr:>7.1f}% win rate")
    
    # Adjacent bucket wins
    print(f"\n  Adjacent bucket analysis:")
    print(f"  - Would win on bucket-1 (below): {adj_below_wins} times ({adj_below_wins/n*100:.1f}%)")
    print(f"  - Would win on bucket+1 (above): {adj_above_wins} times ({adj_above_wins/n*100:.1f}%)")
    print(f"  - Would win on EITHER adjacent: {adj_below_wins + adj_above_wins} times ({(adj_below_wins+adj_above_wins)/n*100:.1f}%)")
    
    # Win rate breakdown
    s1_wr = s1_wins / n * 100
    s2_wr = s2_wins / n * 100
    s3_wr = s3_wins / n * 100
    s4_wr = s4_wins / n * 100
    
    print("\n" + "=" * 65)
    print("  RECOMMENDATION")
    print("=" * 65)
    
    print(f"\n  Single bucket win rate: {s1_wr:.1f}%")
    print(f"  2-bucket BELOW win rate: {s2_wr:.1f}% (diff: {s2_wr-s1_wr:+.1f}%)")
    print(f"  2-bucket ABOVE win rate: {s3_wr:.1f}% (diff: {s3_wr-s1_wr:+.1f}%)")
    print(f"  3-bucket win rate: {s4_wr:.1f}% (diff: {s4_wr-s1_wr:+.1f}%)")
    
    print(f"\n  Single bucket avg P/L: ${s1_profit/n:.3f}")
    print(f"  2-bucket BELOW avg P/L: ${s2_profit/n:.3f}")
    print(f"  2-bucket ABOVE avg P/L: ${s3_profit/n:.3f}")
    print(f"  3-bucket avg P/L: ${s4_profit/n:.3f}")
    
    # Determine recommendation
    wr_improvement = max(s2_wr, s3_wr, s4_wr) - s1_wr
    profit_improvement = max(s2_profit, s3_profit, s4_profit) - s1_profit
    
    print("\n  " + "=" * 63)
    if wr_improvement >= 10 and profit_improvement >= 0.1:
        print("  ✓ RECOMMEND 2-BUCKET STRATEGY")
        print(f"    - Win rate improves by {wr_improvement:.1f}%")
        print(f"    - Profit improves by ${profit_improvement:.2f}")
    elif wr_improvement >= 5:
        print("  ~ CONSIDER 2-BUCKET with caveats")
        print(f"    - Win rate improves by {wr_improvement:.1f}%")
        print(f"    - But check if reduced payout compensates")
    elif wr_improvement > 0:
        print("  ~ MARGINAL benefit from 2-bucket")
        print(f"    - Win rate only improves by {wr_improvement:.1f}%")
        print(f"    - May not be worth the complexity")
    else:
        print("  ✗ KEEP SINGLE BUCKET STRATEGY")
        print(f"    - 2-bucket reduces win rate by {-wr_improvement:.1f}%")
        print(f"    - Single bucket remains superior")
    
    print("  " + "=" * 63)
    
    # Save results
    output = {
        'generated_at': datetime.now().isoformat(),
        'sigma_used': SIGMA,
        'total_trades': n,
        'strategies': {
            'single_bucket': {
                'wins': s1_wins, 'losses': s1_losses,
                'win_rate': round(s1_wr, 2),
                'total_profit': round(s1_profit, 2),
                'avg_profit_per_trade': round(s1_profit/n, 4)
            },
            'two_bucket_below': {
                'wins': s2_wins, 'losses': s2_losses,
                'win_rate': round(s2_wr, 2),
                'total_profit': round(s2_profit, 2),
                'avg_profit_per_trade': round(s2_profit/n, 4)
            },
            'two_bucket_above': {
                'wins': s3_wins, 'losses': s3_losses,
                'win_rate': round(s3_wr, 2),
                'total_profit': round(s3_profit, 2),
                'avg_profit_per_trade': round(s3_profit/n, 4)
            },
            'three_bucket': {
                'wins': s4_wins, 'losses': s4_losses,
                'win_rate': round(s4_wr, 2),
                'total_profit': round(s4_profit, 2),
                'avg_profit_per_trade': round(s4_profit/n, 4)
            }
        },
        'error_distance': {str(k): v for k, v in error_distances.items()},
        'adjacent_bucket_wins': {
            'below': adj_below_wins,
            'above': adj_above_wins
        }
    }
    
    out_file = f'{DATA_DIR}/two_bucket_backtest_results.json'
    with open(out_file, 'w') as f:
        json.dump(output, f, indent=2)
    print(f"\nResults saved to: {out_file}")
    
    return output

if __name__ == '__main__':
    results = run_backtest()
