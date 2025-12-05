#!/usr/bin/env python3
"""
BTC/USDT 完整策略分析 v2 - 扩展版
增加更多策略组合，放宽筛选条件
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "/home/user/zk-2048/trading_strategy/data"
OUTPUT_DIR = "/home/user/zk-2048/trading_strategy"


class TechnicalIndicators:
    @staticmethod
    def ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series, period):
        return series.rolling(window=period).mean()

    @staticmethod
    def rsi(series, period=14):
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series, fast=12, slow=26, signal=9):
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        return dif, dea, (dif - dea) * 2

    @staticmethod
    def bollinger_bands(series, period=20, std_dev=2):
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        return middle + (std * std_dev), middle, middle - (std * std_dev)


def load_data():
    print("=" * 60)
    print("Phase 1: 加载数据")
    print("=" * 60)

    data = {}

    for tf in ['1d', '4h', '1h', '1w']:
        filepath = f"{DATA_DIR}/BTCUSDT_{tf}.csv"
        if os.path.exists(filepath):
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            data[tf] = df
            print(f"  {tf}: {len(df)} 条, {df['timestamp'].min().date()} ~ {df['timestamp'].max().date()}")

    fng_path = f"{DATA_DIR}/fear_greed_index.csv"
    if os.path.exists(fng_path):
        fng = pd.read_csv(fng_path)
        fng['timestamp'] = pd.to_datetime(fng['timestamp'])
        fng['value'] = pd.to_numeric(fng['value'], errors='coerce')
        data['fng'] = fng
        print(f"  恐惧贪婪: {len(fng)} 条")

    funding_path = f"{DATA_DIR}/BTCUSDT_funding_rate.csv"
    if os.path.exists(funding_path):
        funding = pd.read_csv(funding_path)
        funding['fundingTime'] = pd.to_datetime(funding['fundingTime'])
        funding['fundingRate'] = pd.to_numeric(funding['fundingRate'], errors='coerce')
        data['funding'] = funding
        print(f"  资金费率: {len(funding)} 条")

    return data


def add_indicators(df):
    df = df.copy()
    c, h, l, o, v = df['close'], df['high'], df['low'], df['open'], df['volume']

    for p in [7, 25, 50, 99, 200]:
        df[f'ema_{p}'] = TechnicalIndicators.ema(c, p)

    df['rsi_14'] = TechnicalIndicators.rsi(c, 14)
    df['macd_dif'], df['macd_dea'], df['macd_hist'] = TechnicalIndicators.macd(c)
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = TechnicalIndicators.bollinger_bands(c)

    df['vol_ma20'] = TechnicalIndicators.sma(v, 20)
    df['vol_ratio'] = v / df['vol_ma20']

    df['body'] = abs(c - o)
    df['upper_shadow'] = h - np.maximum(c, o)
    df['lower_shadow'] = np.minimum(c, o) - l
    df['amplitude'] = (h - l) / o * 100
    df['change_pct'] = c.pct_change() * 100

    # 交叉信号
    df['ema7_above_25'] = df['ema_7'] > df['ema_25']
    df['ema7_cross_up'] = df['ema7_above_25'] & ~df['ema7_above_25'].shift(1).fillna(False)
    df['ema7_cross_down'] = ~df['ema7_above_25'] & df['ema7_above_25'].shift(1).fillna(True)

    df['macd_above'] = df['macd_dif'] > df['macd_dea']
    df['macd_golden'] = df['macd_above'] & ~df['macd_above'].shift(1).fillna(False)
    df['macd_death'] = ~df['macd_above'] & df['macd_above'].shift(1).fillna(True)

    # 插针
    df['pin_bullish'] = (df['lower_shadow'] > df['body'] * 2) & (df['upper_shadow'] < df['body'] * 0.5)
    df['pin_bearish'] = (df['upper_shadow'] > df['body'] * 2) & (df['lower_shadow'] < df['body'] * 0.5)

    # 连续涨跌
    df['up'] = df['change_pct'] > 0
    df['cons_up'] = df['up'].groupby((~df['up']).cumsum()).cumsum()
    df['cons_down'] = (~df['up']).groupby(df['up'].cumsum()).cumsum()

    # 价格位置
    df['near_ema25'] = abs(c - df['ema_25']) / df['ema_25'] < 0.02
    df['above_ema99'] = c > df['ema_99']
    df['below_ema99'] = c < df['ema_99']

    return df


def merge_external(df, fng_df, funding_df):
    df = df.copy()
    df['date'] = df['timestamp'].dt.date

    if fng_df is not None:
        fng = fng_df[['timestamp', 'value']].copy()
        fng['date'] = fng['timestamp'].dt.date
        fng = fng.rename(columns={'value': 'fear_greed'})
        df = df.merge(fng[['date', 'fear_greed']], on='date', how='left')
        df['fear_greed'] = df['fear_greed'].fillna(method='ffill').fillna(50)

    if funding_df is not None:
        funding = funding_df[['fundingTime', 'fundingRate']].copy()
        funding['date'] = funding['fundingTime'].dt.date
        daily = funding.groupby('date')['fundingRate'].mean().reset_index()
        df = df.merge(daily, on='date', how='left')
        df['fundingRate'] = df['fundingRate'].fillna(0)

    return df


def backtest(df, signals, direction='long', tp_pct=50, sl_pct=20, leverage=10, max_hold=30):
    trades = []
    position = None
    tp_spot = tp_pct / leverage / 100
    sl_spot = sl_pct / leverage / 100

    vals = df[['timestamp', 'open', 'high', 'low', 'close']].values
    sigs = signals.values

    for i in range(len(df) - max_hold - 1):
        if position is None and sigs[i]:
            position = {
                'idx': i + 1,
                'price': vals[i + 1, 1],
                'time': vals[i + 1, 0]
            }
        elif position is not None:
            j = i + 1
            _, _, high, low, close = vals[j]
            entry = position['price']

            if direction == 'long':
                tp_p, sl_p = entry * (1 + tp_spot), entry * (1 - sl_spot)
                hit_tp, hit_sl = high >= tp_p, low <= sl_p
            else:
                tp_p, sl_p = entry * (1 - tp_spot), entry * (1 + sl_spot)
                hit_tp, hit_sl = low <= tp_p, high >= sl_p

            exit_p, reason = None, None
            if hit_sl and hit_tp:
                exit_p, reason = sl_p, 'sl'
            elif hit_sl:
                exit_p, reason = sl_p, 'sl'
            elif hit_tp:
                exit_p, reason = tp_p, 'tp'
            elif j - position['idx'] >= max_hold:
                exit_p, reason = close, 'timeout'

            if reason:
                ret = ((exit_p - entry) / entry if direction == 'long' else (entry - exit_p) / entry) * leverage * 100
                trades.append({'return': ret, 'reason': reason})
                position = None

    return trades


def calc_metrics(trades, min_trades=5):
    if len(trades) < min_trades:
        return None

    rets = [t['return'] for t in trades]
    wins = [r for r in rets if r > 0]
    losses = [r for r in rets if r <= 0]

    n = len(trades)
    wr = len(wins) / n * 100
    avg_w = np.mean(wins) if wins else 0
    avg_l = abs(np.mean(losses)) if losses else 0
    ev = (wr / 100 * avg_w) - ((1 - wr / 100) * avg_l)
    plr = avg_w / avg_l if avg_l > 0 else 999

    return {
        'n': n,
        'wr': round(wr, 1),
        'avg_w': round(avg_w, 1),
        'avg_l': round(avg_l, 1),
        'ev': round(ev, 2),
        'plr': round(plr, 2),
        'total': round(sum(rets), 1)
    }


def run_scan(data):
    print("\n" + "=" * 60)
    print("Phase 2-4: 策略扫描")
    print("=" * 60)

    results = []
    fng_df = data.get('fng')
    funding_df = data.get('funding')

    def get_conds(df):
        return {
            # 恐惧贪婪 - 做多
            'FNG≤10': df['fear_greed'] <= 10,
            'FNG≤15': df['fear_greed'] <= 15,
            'FNG≤20': df['fear_greed'] <= 20,
            'FNG≤25': df['fear_greed'] <= 25,
            'FNG≤30': df['fear_greed'] <= 30,
            'FNG≤35': df['fear_greed'] <= 35,
            # 恐惧贪婪 - 做空
            'FNG≥70': df['fear_greed'] >= 70,
            'FNG≥75': df['fear_greed'] >= 75,
            'FNG≥80': df['fear_greed'] >= 80,
            'FNG≥85': df['fear_greed'] >= 85,

            # RSI
            'RSI<25': df['rsi_14'] < 25,
            'RSI<30': df['rsi_14'] < 30,
            'RSI<35': df['rsi_14'] < 35,
            'RSI>65': df['rsi_14'] > 65,
            'RSI>70': df['rsi_14'] > 70,
            'RSI>75': df['rsi_14'] > 75,

            # EMA/MACD
            'EMA7金叉': df['ema7_cross_up'],
            'EMA7死叉': df['ema7_cross_down'],
            'MACD金叉': df['macd_golden'],
            'MACD死叉': df['macd_death'],
            '回踩EMA25': df['near_ema25'],
            '站上EMA99': df['above_ema99'],
            '跌破EMA99': df['below_ema99'],

            # 涨跌幅
            '跌>3%': df['change_pct'] < -3,
            '跌>5%': df['change_pct'] < -5,
            '跌>8%': df['change_pct'] < -8,
            '跌>10%': df['change_pct'] < -10,
            '涨>3%': df['change_pct'] > 3,
            '涨>5%': df['change_pct'] > 5,
            '涨>8%': df['change_pct'] > 8,

            # 插针
            '下插针3%': df['pin_bullish'] & (df['amplitude'] > 3),
            '下插针5%': df['pin_bullish'] & (df['amplitude'] > 5),
            '上插针3%': df['pin_bearish'] & (df['amplitude'] > 3),
            '上插针5%': df['pin_bearish'] & (df['amplitude'] > 5),

            # 成交量
            '放量2x': df['vol_ratio'] > 2,
            '放量3x': df['vol_ratio'] > 3,
            '缩量': df['vol_ratio'] < 0.5,

            # 资金费率
            '负费率': df['fundingRate'] < -0.0001,
            '强负费率': df['fundingRate'] < -0.0005,
            '正费率': df['fundingRate'] > 0.0005,
            '强正费率': df['fundingRate'] > 0.001,

            # 连续
            '连跌3': df['cons_down'] >= 3,
            '连跌4': df['cons_down'] >= 4,
            '连涨3': df['cons_up'] >= 3,
            '连涨4': df['cons_up'] >= 4,

            # 布林带
            '触BB下轨': df['close'] < df['bb_lower'],
            '触BB上轨': df['close'] > df['bb_upper'],
        }

    tp_sl = [(30, 10), (50, 15), (50, 20), (80, 20), (100, 20), (100, 25), (150, 30)]

    long_kw = ['FNG≤', 'RSI<', '金叉', '下插针', '跌>', '负费率', '连跌', 'BB下轨', '回踩', '站上']

    cnt = 0

    # 单维度
    print("\n--- 单维度 ---")
    for tf in ['1d', '4h', '1h']:
        if tf not in data:
            continue
        df = add_indicators(data[tf])
        df = merge_external(df, fng_df, funding_df)
        conds = get_conds(df)

        for name, sig in conds.items():
            dir_ = 'long' if any(k in name for k in long_kw) else 'short'
            for tp, sl in tp_sl:
                trades = backtest(df, sig, dir_, tp, sl)
                m = calc_metrics(trades, min_trades=8)
                cnt += 1
                if m and m['wr'] >= 45 and m['ev'] > 0:
                    results.append({'name': f"{tf}_{name}", 'tf': tf, 'dir': dir_, 'tp': tp, 'sl': sl, **m})

    print(f"  单维度: {cnt} 次")

    # 双维度
    print("\n--- 双维度 ---")
    fng_l = ['FNG≤15', 'FNG≤20', 'FNG≤25', 'FNG≤30']
    tech_l = ['RSI<30', 'RSI<35', 'EMA7金叉', 'MACD金叉', '下插针5%', '回踩EMA25']
    drop_l = ['跌>3%', '跌>5%', '跌>8%']
    fund_l = ['负费率', '强负费率']
    vol_l = ['放量2x', '放量3x']

    combo_cnt = 0
    for tf in ['1d', '4h']:
        if tf not in data:
            continue
        df = add_indicators(data[tf])
        df = merge_external(df, fng_df, funding_df)
        conds = get_conds(df)

        # FNG + Tech
        for a in fng_l:
            for b in tech_l:
                if a in conds and b in conds:
                    sig = conds[a] & conds[b]
                    for tp, sl in [(50, 20), (80, 20), (100, 20)]:
                        trades = backtest(df, sig, 'long', tp, sl)
                        m = calc_metrics(trades, 5)
                        combo_cnt += 1
                        if m and m['wr'] >= 50 and m['ev'] > 0:
                            results.append({'name': f"{tf}_{a}+{b}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

        # FNG + Drop
        for a in fng_l:
            for b in drop_l:
                if a in conds and b in conds:
                    sig = conds[a] & conds[b]
                    for tp, sl in [(50, 20), (100, 20)]:
                        trades = backtest(df, sig, 'long', tp, sl)
                        m = calc_metrics(trades, 5)
                        combo_cnt += 1
                        if m and m['wr'] >= 50 and m['ev'] > 0:
                            results.append({'name': f"{tf}_{a}+{b}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

        # Drop + Tech
        for a in drop_l:
            for b in tech_l:
                if a in conds and b in conds:
                    sig = conds[a] & conds[b]
                    for tp, sl in [(50, 20), (100, 20)]:
                        trades = backtest(df, sig, 'long', tp, sl)
                        m = calc_metrics(trades, 5)
                        combo_cnt += 1
                        if m and m['wr'] >= 50 and m['ev'] > 0:
                            results.append({'name': f"{tf}_{a}+{b}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

        # Fund + Tech
        for a in fund_l:
            for b in tech_l:
                if a in conds and b in conds:
                    sig = conds[a] & conds[b]
                    for tp, sl in [(50, 20), (80, 20)]:
                        trades = backtest(df, sig, 'long', tp, sl)
                        m = calc_metrics(trades, 5)
                        combo_cnt += 1
                        if m and m['wr'] >= 50 and m['ev'] > 0:
                            results.append({'name': f"{tf}_{a}+{b}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

        # Vol + Drop
        for a in vol_l:
            for b in drop_l:
                if a in conds and b in conds:
                    sig = conds[a] & conds[b]
                    for tp, sl in [(50, 20), (100, 20)]:
                        trades = backtest(df, sig, 'long', tp, sl)
                        m = calc_metrics(trades, 5)
                        combo_cnt += 1
                        if m and m['wr'] >= 50 and m['ev'] > 0:
                            results.append({'name': f"{tf}_{a}+{b}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

    print(f"  双维度: {combo_cnt} 次")

    # 三维度
    print("\n--- 三维度 ---")
    tri_cnt = 0
    for tf in ['1d', '4h']:
        if tf not in data:
            continue
        df = add_indicators(data[tf])
        df = merge_external(df, fng_df, funding_df)
        conds = get_conds(df)

        for a in fng_l[:3]:
            for b in drop_l[:2]:
                for c in tech_l[:4]:
                    if all(x in conds for x in [a, b, c]):
                        sig = conds[a] & conds[b] & conds[c]
                        for tp, sl in [(50, 20), (100, 20)]:
                            trades = backtest(df, sig, 'long', tp, sl)
                            m = calc_metrics(trades, 3)
                            tri_cnt += 1
                            if m and m['wr'] >= 55 and m['ev'] > 0:
                                results.append({'name': f"{tf}_{a}+{b}+{c}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

        for a in fund_l:
            for b in drop_l[:2]:
                for c in tech_l[:3]:
                    if all(x in conds for x in [a, b, c]):
                        sig = conds[a] & conds[b] & conds[c]
                        for tp, sl in [(50, 20), (100, 20)]:
                            trades = backtest(df, sig, 'long', tp, sl)
                            m = calc_metrics(trades, 3)
                            tri_cnt += 1
                            if m and m['wr'] >= 55 and m['ev'] > 0:
                                results.append({'name': f"{tf}_{a}+{b}+{c}", 'tf': tf, 'dir': 'long', 'tp': tp, 'sl': sl, **m})

    print(f"  三维度: {tri_cnt} 次")

    total = cnt + combo_cnt + tri_cnt
    print(f"\n总测试: {total} | 有效策略: {len(results)}")

    return results


def gen_report(results, data):
    print("\n" + "=" * 60)
    print("生成报告")
    print("=" * 60)

    if not results:
        print("无有效策略!")
        return None

    df = pd.DataFrame(results)
    df = df.sort_values('ev', ascending=False).drop_duplicates(subset=['name', 'tp', 'sl']).reset_index(drop=True)
    df.to_csv(f"{OUTPUT_DIR}/strategy_results.csv", index=False)

    kline = data.get('1d')
    date_range = f"{kline['timestamp'].min().strftime('%Y-%m-%d')} ~ {kline['timestamp'].max().strftime('%Y-%m-%d')}" if kline is not None else "N/A"

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 最优EV策略报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
            color: #e6e6e6;
            padding: 30px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ text-align: center; color: #ffd700; font-size: 2.2em; margin-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .stat {{ background: rgba(255,255,255,0.05); border-radius: 10px; padding: 20px; text-align: center; border: 1px solid rgba(255,215,0,0.3); }}
        .stat-val {{ font-size: 2em; color: #ffd700; font-weight: bold; }}
        .stat-lbl {{ color: #8b949e; margin-top: 5px; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0; background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden; }}
        th {{ background: rgba(255,215,0,0.15); color: #ffd700; padding: 12px 8px; text-align: left; }}
        td {{ padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        tr:hover {{ background: rgba(255,215,0,0.05); }}
        .rank {{ color: #ffd700; font-weight: bold; }}
        .pos {{ color: #3fb950; }}
        .neg {{ color: #f85149; }}
        .tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; margin: 1px; }}
        .tag-l {{ background: #3fb950; color: #fff; }}
        .tag-s {{ background: #f85149; color: #fff; }}
        .tag-t {{ background: #1f6feb; color: #fff; }}
        .section {{ background: rgba(255,255,255,0.03); border-radius: 15px; padding: 25px; margin: 20px 0; border: 1px solid rgba(255,215,0,0.2); }}
        .section-title {{ color: #ffd700; font-size: 1.3em; margin-bottom: 15px; border-bottom: 1px solid rgba(255,215,0,0.3); padding-bottom: 10px; }}
        .formula {{ background: rgba(0,0,0,0.5); border: 1px solid #ffd700; border-radius: 10px; padding: 15px; margin: 15px 0; font-family: monospace; }}
        .highlight {{ background: rgba(255,215,0,0.1); padding: 15px; border-radius: 10px; margin: 10px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 最优EV策略报告</h1>
        <p class="subtitle">数据范围: {date_range} | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

        <div class="stats">
            <div class="stat"><div class="stat-val">{len(df)}</div><div class="stat-lbl">有效策略</div></div>
            <div class="stat"><div class="stat-val">{df['wr'].max():.1f}%</div><div class="stat-lbl">最高胜率</div></div>
            <div class="stat"><div class="stat-val">{df['ev'].max():.2f}%</div><div class="stat-lbl">最高EV</div></div>
            <div class="stat"><div class="stat-val">{df['plr'].max():.2f}</div><div class="stat-lbl">最高盈亏比</div></div>
            <div class="stat"><div class="stat-val">{df['n'].sum()}</div><div class="stat-lbl">总交易次数</div></div>
        </div>

        <div class="section">
            <div class="section-title">EV计算公式</div>
            <div class="formula">
                <strong>EV = (胜率 × 平均盈利%) - ((1-胜率) × 平均亏损%)</strong><br/><br/>
                • 止盈/止损: 保证金盈亏% (10x杠杆)<br/>
                • 例: TP50%=现货涨5%, SL20%=现货跌2%
            </div>
        </div>

        <div class="section">
            <div class="section-title">TOP 50 最优EV策略</div>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>周期</th>
                    <th>方向</th>
                    <th>TP/SL</th>
                    <th>次数</th>
                    <th>胜率</th>
                    <th>盈利</th>
                    <th>亏损</th>
                    <th>EV</th>
                    <th>盈亏比</th>
                    <th>总收益</th>
                </tr>
'''

    for i, row in df.head(50).iterrows():
        d_tag = '<span class="tag tag-l">多</span>' if row['dir'] == 'long' else '<span class="tag tag-s">空</span>'
        ev_c = 'pos' if row['ev'] > 0 else 'neg'

        html += f'''
                <tr>
                    <td class="rank">{i + 1}</td>
                    <td>{row['name']}</td>
                    <td><span class="tag tag-t">{row['tf']}</span></td>
                    <td>{d_tag}</td>
                    <td>{row['tp']}%/{row['sl']}%</td>
                    <td>{row['n']}</td>
                    <td class="pos">{row['wr']}%</td>
                    <td class="pos">+{row['avg_w']}%</td>
                    <td class="neg">-{row['avg_l']}%</td>
                    <td class="{ev_c}">{row['ev']}%</td>
                    <td>{row['plr']}</td>
                    <td class="{'pos' if row['total']>0 else 'neg'}">{row['total']}%</td>
                </tr>
'''

    # 策略分类汇总
    by_type = df.groupby(df['name'].str.split('_').str[1].str.split('+').str[0]).agg({
        'ev': 'mean', 'wr': 'mean', 'n': 'sum'
    }).sort_values('ev', ascending=False).head(10)

    html += '''
            </table>
        </div>

        <div class="section">
            <div class="section-title">策略类型EV排名</div>
            <div class="highlight">
'''
    for cond, row in by_type.iterrows():
        html += f'''<p><strong>{cond}</strong>: 平均EV {row['ev']:.2f}%, 平均胜率 {row['wr']:.1f}%, 总交易 {int(row['n'])}次</p>'''

    html += '''
            </div>
        </div>

        <div class="section">
            <div class="section-title">Top 5 策略详解</div>
            <ul style="margin-left:20px; line-height:2;">
'''
    for i, row in df.head(5).iterrows():
        html += f'''
                <li><strong>【{i+1}】{row['name']}</strong><br/>
                    周期:{row['tf']} | 方向:{'做多' if row['dir']=='long' else '做空'} |
                    TP/SL:{row['tp']}%/{row['sl']}% |
                    胜率:{row['wr']}% | EV:{row['ev']}% |
                    交易{row['n']}次 | 盈亏比{row['plr']}
                </li>
'''

    html += '''
            </ul>
        </div>

        <div class="section">
            <div class="section-title">风险提示</div>
            <ul style="margin-left:20px; line-height:1.8; color:#d29922;">
                <li>历史回测≠未来收益</li>
                <li>实盘有滑点、手续费成本</li>
                <li>建议半凯利仓位控制风险</li>
                <li>单笔最大亏损≤总资金10%</li>
            </ul>
        </div>

        <div style="text-align:center; margin-top:40px; color:#8b949e;">
            <p>BTC/USDT 最优EV策略报告 v2.0</p>
            <p>''' + datetime.now().strftime('%Y年%m月%d日') + '''</p>
        </div>
    </div>
</body>
</html>
'''

    path = f"{OUTPUT_DIR}/最优EV策略报告.html"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告: {path}")
    return path


def main():
    data = load_data()
    if not data:
        return None
    results = run_scan(data)
    if results:
        return gen_report(results, data)
    return None


if __name__ == "__main__":
    main()
