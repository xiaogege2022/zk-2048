#!/usr/bin/env python3
"""
BTC/USDT 完整策略分析 - 基于您提供的K线数据
遍历策略组合，计算EV，回测验证，生成报告
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import warnings
import itertools
warnings.filterwarnings('ignore')

DATA_DIR = "/home/user/zk-2048/trading_strategy/data"
OUTPUT_DIR = "/home/user/zk-2048/trading_strategy"


class TechnicalIndicators:
    """技术指标计算器"""

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
        macd_hist = (dif - dea) * 2
        return dif, dea, macd_hist

    @staticmethod
    def bollinger_bands(series, period=20, std_dev=2):
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower


def load_and_prepare_data():
    """加载并准备所有数据"""
    print("=" * 60)
    print("Phase 1: 加载数据")
    print("=" * 60)

    data = {}

    # 加载K线数据
    for tf in ['1d', '4h', '1h', '1w']:
        filepath = f"{DATA_DIR}/BTCUSDT_{tf}.csv"
        if os.path.exists(filepath):
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            # 确保数值类型
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')

            data[tf] = df
            print(f"  {tf}: {len(df)} 条记录, {df['timestamp'].min()} ~ {df['timestamp'].max()}")

    # 加载恐惧贪婪指数
    fng_path = f"{DATA_DIR}/fear_greed_index.csv"
    if os.path.exists(fng_path):
        fng = pd.read_csv(fng_path)
        fng['timestamp'] = pd.to_datetime(fng['timestamp'])
        fng['value'] = pd.to_numeric(fng['value'], errors='coerce')
        data['fng'] = fng
        print(f"  恐惧贪婪指数: {len(fng)} 条记录")

    # 加载资金费率
    funding_path = f"{DATA_DIR}/BTCUSDT_funding_rate.csv"
    if os.path.exists(funding_path):
        funding = pd.read_csv(funding_path)
        funding['fundingTime'] = pd.to_datetime(funding['fundingTime'])
        funding['fundingRate'] = pd.to_numeric(funding['fundingRate'], errors='coerce')
        data['funding'] = funding
        print(f"  资金费率: {len(funding)} 条记录")

    # 加载OI
    oi_path = f"{DATA_DIR}/BTCUSDT_open_interest.csv"
    if os.path.exists(oi_path):
        oi = pd.read_csv(oi_path)
        data['oi'] = oi
        print(f"  OI持仓量: {len(oi)} 条记录")

    return data


def add_indicators(df, timeframe):
    """添加技术指标"""
    df = df.copy()
    close = df['close']
    high = df['high']
    low = df['low']
    volume = df['volume']
    open_price = df['open']

    # EMA
    for period in [7, 25, 50, 99, 200]:
        df[f'ema_{period}'] = TechnicalIndicators.ema(close, period)

    # RSI
    df['rsi_14'] = TechnicalIndicators.rsi(close, 14)

    # MACD
    df['macd_dif'], df['macd_dea'], df['macd_hist'] = TechnicalIndicators.macd(close)

    # 布林带
    df['bb_upper'], df['bb_middle'], df['bb_lower'] = TechnicalIndicators.bollinger_bands(close)

    # 成交量
    df['vol_ma20'] = TechnicalIndicators.sma(volume, 20)
    df['vol_ratio'] = volume / df['vol_ma20']

    # K线形态
    df['body'] = abs(close - open_price)
    df['upper_shadow'] = high - np.maximum(close, open_price)
    df['lower_shadow'] = np.minimum(close, open_price) - low
    df['amplitude'] = (high - low) / open_price * 100

    # 涨跌幅
    df['change_pct'] = close.pct_change() * 100

    # EMA交叉
    df['ema7_above_ema25'] = df['ema_7'] > df['ema_25']
    df['ema7_cross_up'] = df['ema7_above_ema25'] & ~df['ema7_above_ema25'].shift(1).fillna(False)
    df['ema7_cross_down'] = ~df['ema7_above_ema25'] & df['ema7_above_ema25'].shift(1).fillna(True)

    # MACD交叉
    df['macd_above'] = df['macd_dif'] > df['macd_dea']
    df['macd_golden'] = df['macd_above'] & ~df['macd_above'].shift(1).fillna(False)
    df['macd_death'] = ~df['macd_above'] & df['macd_above'].shift(1).fillna(True)

    # 插针
    df['pin_bullish'] = (df['lower_shadow'] > df['body'] * 2) & (df['upper_shadow'] < df['body'] * 0.5)
    df['pin_bearish'] = (df['upper_shadow'] > df['body'] * 2) & (df['lower_shadow'] < df['body'] * 0.5)

    # 连续涨跌
    df['up_day'] = df['change_pct'] > 0
    df['consecutive_up'] = df['up_day'].groupby((~df['up_day']).cumsum()).cumsum()
    df['consecutive_down'] = (~df['up_day']).groupby(df['up_day'].cumsum()).cumsum()

    return df


def merge_external_data(df, fng_df, funding_df):
    """合并外部数据"""
    df = df.copy()
    df['date'] = df['timestamp'].dt.date

    # 合并恐惧贪婪指数
    if fng_df is not None:
        fng = fng_df[['timestamp', 'value']].copy()
        fng['date'] = fng['timestamp'].dt.date
        fng = fng.rename(columns={'value': 'fear_greed'})
        df = df.merge(fng[['date', 'fear_greed']], on='date', how='left')
        df['fear_greed'] = df['fear_greed'].fillna(method='ffill').fillna(50)

    # 合并资金费率
    if funding_df is not None:
        funding = funding_df[['fundingTime', 'fundingRate']].copy()
        funding['date'] = funding['fundingTime'].dt.date
        daily_funding = funding.groupby('date')['fundingRate'].mean().reset_index()
        df = df.merge(daily_funding, on='date', how='left')
        df['fundingRate'] = df['fundingRate'].fillna(0)

    return df


def backtest_strategy(df, entry_signals, direction='long',
                      tp_pct=50, sl_pct=20, leverage=10, max_hold=30):
    """
    回测策略
    tp_pct, sl_pct: 保证金盈亏%
    """
    trades = []
    position = None

    tp_spot = tp_pct / leverage / 100
    sl_spot = sl_pct / leverage / 100

    df_values = df[['timestamp', 'open', 'high', 'low', 'close']].values
    signals = entry_signals.values

    for i in range(len(df) - max_hold - 1):
        if position is None and signals[i]:
            entry_price = df_values[i + 1, 1]  # next bar open
            position = {
                'entry_idx': i + 1,
                'entry_price': entry_price,
                'entry_time': df_values[i + 1, 0],
                'highest': entry_price,
                'lowest': entry_price
            }

        elif position is not None:
            idx = i + 1
            _, _, high, low, close = df_values[idx]
            entry_price = position['entry_price']

            position['highest'] = max(position['highest'], high)
            position['lowest'] = min(position['lowest'], low)

            if direction == 'long':
                tp_price = entry_price * (1 + tp_spot)
                sl_price = entry_price * (1 - sl_spot)
                hit_tp = high >= tp_price
                hit_sl = low <= sl_price
            else:
                tp_price = entry_price * (1 - tp_spot)
                sl_price = entry_price * (1 + sl_spot)
                hit_tp = low <= tp_price
                hit_sl = high >= sl_price

            exit_reason = None
            exit_price = None

            if hit_sl and hit_tp:
                exit_reason = 'stop_loss'
                exit_price = sl_price
            elif hit_sl:
                exit_reason = 'stop_loss'
                exit_price = sl_price
            elif hit_tp:
                exit_reason = 'take_profit'
                exit_price = tp_price
            elif idx - position['entry_idx'] >= max_hold:
                exit_reason = 'timeout'
                exit_price = close

            if exit_reason:
                if direction == 'long':
                    spot_return = (exit_price - entry_price) / entry_price
                else:
                    spot_return = (entry_price - exit_price) / entry_price

                margin_return = spot_return * leverage

                trades.append({
                    'entry_time': position['entry_time'],
                    'entry_price': entry_price,
                    'exit_price': exit_price,
                    'exit_reason': exit_reason,
                    'margin_return': margin_return * 100,
                    'hold_bars': idx - position['entry_idx']
                })
                position = None

    return trades


def calculate_metrics(trades):
    """计算策略指标"""
    if not trades:
        return None

    n = len(trades)
    returns = [t['margin_return'] for t in trades]
    wins = [r for r in returns if r > 0]
    losses = [r for r in returns if r <= 0]

    win_rate = len(wins) / n * 100
    avg_win = np.mean(wins) if wins else 0
    avg_loss = abs(np.mean(losses)) if losses else 0
    ev = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)
    plr = avg_win / avg_loss if avg_loss > 0 else 999

    return {
        'n_trades': n,
        'win_rate': round(win_rate, 2),
        'avg_win': round(avg_win, 2),
        'avg_loss': round(avg_loss, 2),
        'ev': round(ev, 2),
        'profit_loss_ratio': round(plr, 2),
        'total_return': round(sum(returns), 2)
    }


def run_strategy_scan(data):
    """运行策略扫描"""
    print("\n" + "=" * 60)
    print("Phase 2-4: 策略遍历与回测")
    print("=" * 60)

    results = []
    test_count = 0

    # 准备数据
    timeframes = ['1d', '4h', '1h']
    fng_df = data.get('fng')
    funding_df = data.get('funding')

    # 定义条件
    def get_conditions(df):
        return {
            # 恐惧贪婪 (做多信号)
            'FNG_极度恐惧≤10': df['fear_greed'] <= 10,
            'FNG_极度恐惧≤15': df['fear_greed'] <= 15,
            'FNG_恐惧≤20': df['fear_greed'] <= 20,
            'FNG_恐惧≤25': df['fear_greed'] <= 25,
            'FNG_恐惧≤30': df['fear_greed'] <= 30,
            # 恐惧贪婪 (做空信号)
            'FNG_贪婪≥75': df['fear_greed'] >= 75,
            'FNG_极度贪婪≥85': df['fear_greed'] >= 85,
            'FNG_极度贪婪≥90': df['fear_greed'] >= 90,

            # 技术指标
            'RSI超卖<30': df['rsi_14'] < 30,
            'RSI极度超卖<20': df['rsi_14'] < 20,
            'RSI超买>70': df['rsi_14'] > 70,
            'RSI极度超买>80': df['rsi_14'] > 80,
            'EMA7金叉EMA25': df['ema7_cross_up'],
            'EMA7死叉EMA25': df['ema7_cross_down'],
            'MACD金叉': df['macd_golden'],
            'MACD死叉': df['macd_death'],
            '价格触及布林下轨': df['close'] < df['bb_lower'],
            '价格触及布林上轨': df['close'] > df['bb_upper'],

            # 涨跌幅
            '日跌幅>5%': df['change_pct'] < -5,
            '日跌幅>8%': df['change_pct'] < -8,
            '日跌幅>10%': df['change_pct'] < -10,
            '日跌幅>15%': df['change_pct'] < -15,
            '日涨幅>5%': df['change_pct'] > 5,
            '日涨幅>10%': df['change_pct'] > 10,

            # 插针
            '下插针振幅>3%': df['pin_bullish'] & (df['amplitude'] > 3),
            '下插针振幅>5%': df['pin_bullish'] & (df['amplitude'] > 5),
            '下插针振幅>8%': df['pin_bullish'] & (df['amplitude'] > 8),
            '上插针振幅>3%': df['pin_bearish'] & (df['amplitude'] > 3),
            '上插针振幅>5%': df['pin_bearish'] & (df['amplitude'] > 5),

            # 成交量
            '放量>2倍': df['vol_ratio'] > 2,
            '放量>3倍': df['vol_ratio'] > 3,
            '缩量<0.5倍': df['vol_ratio'] < 0.5,

            # 资金费率
            '负费率<-0.01%': df['fundingRate'] < -0.0001,
            '负费率<-0.05%': df['fundingRate'] < -0.0005,
            '负费率<-0.1%': df['fundingRate'] < -0.001,
            '正费率>0.1%': df['fundingRate'] > 0.001,
            '正费率>0.2%': df['fundingRate'] > 0.002,

            # 连续涨跌
            '连跌3天': df['consecutive_down'] >= 3,
            '连跌5天': df['consecutive_down'] >= 5,
            '连涨3天': df['consecutive_up'] >= 3,
            '连涨5天': df['consecutive_up'] >= 5,
        }

    # 止盈止损组合
    tp_sl_combos = [
        (30, 10), (50, 15), (50, 20), (80, 20), (100, 20), (100, 30), (150, 30)
    ]

    # 做多条件关键词
    long_keywords = ['恐惧', '超卖', '金叉', '下插针', '跌幅', '负费率', '连跌', '布林下轨']
    short_keywords = ['贪婪', '超买', '死叉', '上插针', '涨幅', '正费率', '连涨', '布林上轨']

    print("\n--- 单维度策略测试 ---")

    for tf in timeframes:
        if tf not in data:
            continue

        df = data[tf].copy()
        df = add_indicators(df, tf)
        df = merge_external_data(df, fng_df, funding_df)

        conditions = get_conditions(df)

        for cond_name, signals in conditions.items():
            # 判断方向
            direction = 'long' if any(kw in cond_name for kw in long_keywords) else 'short'

            for tp, sl in tp_sl_combos:
                trades = backtest_strategy(df, signals, direction, tp, sl)
                metrics = calculate_metrics(trades)
                test_count += 1

                if metrics and metrics['n_trades'] >= 10 and metrics['win_rate'] >= 50:
                    results.append({
                        'strategy': f"{tf}_{cond_name}",
                        'timeframe': tf,
                        'direction': direction,
                        'tp_pct': tp,
                        'sl_pct': sl,
                        **metrics
                    })

    print(f"  单维度测试完成: {test_count} 次")

    # 双维度组合测试
    print("\n--- 双维度策略测试 ---")
    combo_count = 0

    # 重点组合
    fng_long = ['FNG_极度恐惧≤10', 'FNG_极度恐惧≤15', 'FNG_恐惧≤20', 'FNG_恐惧≤25']
    tech_long = ['RSI超卖<30', 'RSI极度超卖<20', 'EMA7金叉EMA25', 'MACD金叉', '下插针振幅>5%']
    drop_conds = ['日跌幅>5%', '日跌幅>8%', '日跌幅>10%']
    funding_long = ['负费率<-0.01%', '负费率<-0.05%']

    for tf in ['1d', '4h']:
        if tf not in data:
            continue

        df = data[tf].copy()
        df = add_indicators(df, tf)
        df = merge_external_data(df, fng_df, funding_df)
        conditions = get_conditions(df)

        # FNG + 技术指标
        for fng in fng_long:
            for tech in tech_long:
                if fng in conditions and tech in conditions:
                    combined = conditions[fng] & conditions[tech]
                    for tp, sl in [(50, 20), (100, 20), (80, 15)]:
                        trades = backtest_strategy(df, combined, 'long', tp, sl)
                        metrics = calculate_metrics(trades)
                        combo_count += 1

                        if metrics and metrics['n_trades'] >= 5 and metrics['win_rate'] >= 55:
                            results.append({
                                'strategy': f"{tf}_{fng}+{tech}",
                                'timeframe': tf,
                                'direction': 'long',
                                'tp_pct': tp,
                                'sl_pct': sl,
                                **metrics
                            })

        # FNG + 跌幅
        for fng in fng_long:
            for drop in drop_conds:
                if fng in conditions and drop in conditions:
                    combined = conditions[fng] & conditions[drop]
                    for tp, sl in [(50, 20), (100, 20)]:
                        trades = backtest_strategy(df, combined, 'long', tp, sl)
                        metrics = calculate_metrics(trades)
                        combo_count += 1

                        if metrics and metrics['n_trades'] >= 5 and metrics['win_rate'] >= 55:
                            results.append({
                                'strategy': f"{tf}_{fng}+{drop}",
                                'timeframe': tf,
                                'direction': 'long',
                                'tp_pct': tp,
                                'sl_pct': sl,
                                **metrics
                            })

        # 跌幅 + 技术指标
        for drop in drop_conds:
            for tech in tech_long:
                if drop in conditions and tech in conditions:
                    combined = conditions[drop] & conditions[tech]
                    for tp, sl in [(50, 20), (100, 20)]:
                        trades = backtest_strategy(df, combined, 'long', tp, sl)
                        metrics = calculate_metrics(trades)
                        combo_count += 1

                        if metrics and metrics['n_trades'] >= 5 and metrics['win_rate'] >= 55:
                            results.append({
                                'strategy': f"{tf}_{drop}+{tech}",
                                'timeframe': tf,
                                'direction': 'long',
                                'tp_pct': tp,
                                'sl_pct': sl,
                                **metrics
                            })

    print(f"  双维度测试完成: {combo_count} 次")

    # 三维度组合测试
    print("\n--- 三维度策略测试 ---")
    triple_count = 0

    for tf in ['1d', '4h']:
        if tf not in data:
            continue

        df = data[tf].copy()
        df = add_indicators(df, tf)
        df = merge_external_data(df, fng_df, funding_df)
        conditions = get_conditions(df)

        for fng in fng_long[:3]:
            for drop in drop_conds[:2]:
                for tech in tech_long[:3]:
                    if all(c in conditions for c in [fng, drop, tech]):
                        combined = conditions[fng] & conditions[drop] & conditions[tech]
                        for tp, sl in [(50, 20), (100, 20)]:
                            trades = backtest_strategy(df, combined, 'long', tp, sl)
                            metrics = calculate_metrics(trades)
                            triple_count += 1

                            if metrics and metrics['n_trades'] >= 3 and metrics['win_rate'] >= 60:
                                results.append({
                                    'strategy': f"{tf}_{fng}+{drop}+{tech}",
                                    'timeframe': tf,
                                    'direction': 'long',
                                    'tp_pct': tp,
                                    'sl_pct': sl,
                                    **metrics
                                })

    print(f"  三维度测试完成: {triple_count} 次")

    total = test_count + combo_count + triple_count
    print(f"\n总计测试: {total} 个策略组合")
    print(f"有效策略: {len(results)} 个")

    return results


def generate_report(results, data):
    """生成HTML报告"""
    print("\n" + "=" * 60)
    print("生成最优EV策略报告")
    print("=" * 60)

    if not results:
        print("无有效策略结果!")
        return

    df = pd.DataFrame(results)
    df = df.sort_values('ev', ascending=False).reset_index(drop=True)

    # 保存CSV
    df.to_csv(f"{OUTPUT_DIR}/strategy_results.csv", index=False)

    # 获取数据范围
    kline_1d = data.get('1d')
    date_range = f"{kline_1d['timestamp'].min().strftime('%Y-%m-%d')} ~ {kline_1d['timestamp'].max().strftime('%Y-%m-%d')}" if kline_1d is not None else "N/A"

    # 生成HTML报告
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
        h1 {{
            text-align: center;
            color: #ffd700;
            font-size: 2.2em;
            margin-bottom: 10px;
        }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 30px; }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,215,0,0.3);
        }}
        .stat-value {{
            font-size: 2em;
            color: #ffd700;
            font-weight: bold;
        }}
        .stat-label {{ color: #8b949e; margin-top: 5px; }}
        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: rgba(0,0,0,0.3);
            border-radius: 10px;
            overflow: hidden;
        }}
        th {{
            background: rgba(255,215,0,0.15);
            color: #ffd700;
            padding: 15px 10px;
            text-align: left;
            font-weight: bold;
        }}
        td {{
            padding: 12px 10px;
            border-bottom: 1px solid rgba(255,255,255,0.1);
        }}
        tr:hover {{ background: rgba(255,215,0,0.05); }}
        .rank {{ color: #ffd700; font-weight: bold; }}
        .positive {{ color: #3fb950; }}
        .negative {{ color: #f85149; }}
        .tag {{
            display: inline-block;
            padding: 3px 8px;
            border-radius: 4px;
            font-size: 0.8em;
            margin: 2px;
        }}
        .tag-long {{ background: #3fb950; color: #fff; }}
        .tag-short {{ background: #f85149; color: #fff; }}
        .tag-tf {{ background: #1f6feb; color: #fff; }}
        .section {{
            background: rgba(255,255,255,0.03);
            border-radius: 15px;
            padding: 25px;
            margin: 20px 0;
            border: 1px solid rgba(255,215,0,0.2);
        }}
        .section-title {{
            color: #ffd700;
            font-size: 1.3em;
            margin-bottom: 15px;
            border-bottom: 1px solid rgba(255,215,0,0.3);
            padding-bottom: 10px;
        }}
        .formula-box {{
            background: rgba(0,0,0,0.5);
            border: 1px solid #ffd700;
            border-radius: 10px;
            padding: 15px;
            margin: 15px 0;
            font-family: monospace;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 最优EV策略报告</h1>
        <p class="subtitle">基于 {date_range} 历史数据回测 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(df)}</div>
                <div class="stat-label">有效策略数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{df['win_rate'].max():.1f}%</div>
                <div class="stat-label">最高胜率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{df['ev'].max():.2f}%</div>
                <div class="stat-label">最高EV</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{df['profit_loss_ratio'].max():.2f}</div>
                <div class="stat-label">最高盈亏比</div>
            </div>
        </div>

        <div class="section">
            <div class="section-title">EV计算公式说明</div>
            <div class="formula-box">
                <strong>EV = (胜率 × 平均盈利%) - ((1-胜率) × 平均亏损%)</strong><br/><br/>
                • 止盈%/止损%: 保证金盈亏% (相对于开仓金额)<br/>
                • 杠杆: 10x<br/>
                • 例: 止盈50% = 现货涨5%, 止损20% = 现货跌2%
            </div>
        </div>

        <div class="section">
            <div class="section-title">TOP 30 最优EV策略</div>
            <table>
                <tr>
                    <th>排名</th>
                    <th>策略组合</th>
                    <th>周期</th>
                    <th>方向</th>
                    <th>止盈/止损</th>
                    <th>交易次数</th>
                    <th>胜率</th>
                    <th>平均盈利</th>
                    <th>平均亏损</th>
                    <th>EV</th>
                    <th>盈亏比</th>
                </tr>
'''

    for i, row in df.head(30).iterrows():
        direction_tag = '<span class="tag tag-long">做多</span>' if row['direction'] == 'long' else '<span class="tag tag-short">做空</span>'
        ev_class = 'positive' if row['ev'] > 0 else 'negative'

        html += f'''
                <tr>
                    <td class="rank">{i + 1}</td>
                    <td>{row['strategy']}</td>
                    <td><span class="tag tag-tf">{row['timeframe']}</span></td>
                    <td>{direction_tag}</td>
                    <td>{row['tp_pct']}% / {row['sl_pct']}%</td>
                    <td>{row['n_trades']}</td>
                    <td class="positive">{row['win_rate']:.1f}%</td>
                    <td class="positive">+{row['avg_win']:.1f}%</td>
                    <td class="negative">-{row['avg_loss']:.1f}%</td>
                    <td class="{ev_class}">{row['ev']:.2f}%</td>
                    <td>{row['profit_loss_ratio']:.2f}</td>
                </tr>
'''

    html += '''
            </table>
        </div>

        <div class="section">
            <div class="section-title">策略解读</div>
            <ul style="margin-left:20px; line-height:2;">
'''

    # 添加Top 5策略解读
    for i, row in df.head(5).iterrows():
        html += f'''
                <li><strong>【{i+1}】{row['strategy']}</strong><br/>
                    周期: {row['timeframe']} | 方向: {'做多' if row['direction']=='long' else '做空'} |
                    胜率: {row['win_rate']:.1f}% | EV: {row['ev']:.2f}% |
                    交易{row['n_trades']}次，盈亏比{row['profit_loss_ratio']:.2f}
                </li>
'''

    html += '''
            </ul>
        </div>

        <div class="section">
            <div class="section-title">风险提示</div>
            <ul style="margin-left:20px; line-height:1.8; color:#d29922;">
                <li>历史回测结果不代表未来收益</li>
                <li>实盘交易存在滑点、手续费等成本</li>
                <li>建议使用半凯利仓位，控制风险</li>
                <li>单笔最大亏损不超过总资金10%</li>
            </ul>
        </div>

        <div style="text-align:center; margin-top:40px; color:#8b949e;">
            <p>BTC/USDT 最优EV策略报告 v1.0</p>
            <p>生成时间: ''' + datetime.now().strftime('%Y年%m月%d日') + '''</p>
        </div>
    </div>
</body>
</html>
'''

    report_path = f"{OUTPUT_DIR}/最优EV策略报告.html"
    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告已保存: {report_path}")
    return report_path


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("BTC/USDT 最优EV策略分析系统")
    print("=" * 60)

    # Phase 1: 加载数据
    data = load_and_prepare_data()

    if not data:
        print("数据加载失败!")
        return

    # Phase 2-4: 策略分析与回测
    results = run_strategy_scan(data)

    # 生成报告
    if results:
        report_path = generate_report(results, data)
        return report_path

    return None


if __name__ == "__main__":
    main()
