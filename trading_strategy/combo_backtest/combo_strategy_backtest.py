#!/usr/bin/env python3
"""
BTC/USDT 组合策略回测系统 (优化版)
测试多重条件组合，寻找更高胜率的策略
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
import sys
warnings.filterwarnings('ignore')

# ==================== 数据加载 ====================

def load_data():
    """加载所有数据"""
    print("加载数据...")

    data = {}

    # K线数据
    for tf, file in [('1d', 'BTCUSDT_1d.csv'), ('4h', 'BTCUSDT_4h.csv'), ('1h', 'BTCUSDT_1h.csv')]:
        df = pd.read_csv(file)
        df['timestamp'] = pd.to_datetime(df['timestamp'])
        df = df.sort_values('timestamp').reset_index(drop=True)
        data[tf] = df
        print(f"  {tf}: {len(df):,} K线")

    # 恐惧贪婪指数
    fg = pd.read_csv('fear_greed_index.csv')
    fg['timestamp'] = pd.to_datetime(fg['timestamp'])
    fg = fg.rename(columns={'value': 'fear_greed'})
    data['fear_greed'] = fg
    print(f"  恐惧贪婪: {len(fg):,} 条")

    # 资金费率
    fr = pd.read_csv('BTCUSDT_funding_rate.csv')
    fr['fundingTime'] = pd.to_datetime(fr['fundingTime'])
    fr = fr.rename(columns={'fundingTime': 'timestamp'})
    data['funding'] = fr
    print(f"  资金费率: {len(fr):,} 条")

    return data


# ==================== 技术指标 ====================

def calculate_ema(series, period):
    return series.ewm(span=period, adjust=False).mean()

def calculate_rsi(series, period=14):
    delta = series.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def calculate_macd(series, fast=12, slow=26, signal=9):
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    return macd_line, signal_line

def calculate_bollinger(series, period=20, std=2):
    ma = series.rolling(period).mean()
    std_dev = series.rolling(period).std()
    upper = ma + std * std_dev
    lower = ma - std * std_dev
    return upper, ma, lower

def add_all_indicators(df, fg_data=None, funding_data=None):
    """添加所有技术指标"""
    df = df.copy()

    # EMAs
    df['ema7'] = calculate_ema(df['close'], 7)
    df['ema25'] = calculate_ema(df['close'], 25)
    df['ema50'] = calculate_ema(df['close'], 50)
    df['ema99'] = calculate_ema(df['close'], 99)
    df['ema200'] = calculate_ema(df['close'], 200)

    # RSI
    df['rsi'] = calculate_rsi(df['close'], 14)

    # MACD
    df['macd'], df['macd_signal'] = calculate_macd(df['close'])
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Bollinger Bands
    df['bb_upper'], df['bb_mid'], df['bb_lower'] = calculate_bollinger(df['close'])

    # 价格变化
    df['change_1'] = df['close'].pct_change() * 100
    df['change_3'] = df['close'].pct_change(3) * 100
    df['change_7'] = df['close'].pct_change(7) * 100
    df['change_14'] = df['close'].pct_change(14) * 100

    # 成交量指标
    df['volume_ma20'] = df['volume'].rolling(20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma20']

    # K线形态
    df['body'] = abs(df['close'] - df['open'])
    df['upper_wick'] = df['high'] - df[['open', 'close']].max(axis=1)
    df['lower_wick'] = df[['open', 'close']].min(axis=1) - df['low']
    df['total_range'] = df['high'] - df['low']

    # 趋势指标
    df['uptrend'] = df['close'] > df['ema50']
    df['strong_uptrend'] = (df['close'] > df['ema50']) & (df['ema50'] > df['ema200'])
    df['downtrend'] = df['close'] < df['ema50']

    # EMA交叉信号
    df['ema7_above_25'] = df['ema7'] > df['ema25']
    df['ema7_cross_25'] = df['ema7_above_25'] & (~df['ema7_above_25'].shift(1).fillna(False))
    df['ema50_above_200'] = df['ema50'] > df['ema200']
    df['ema50_cross_200'] = df['ema50_above_200'] & (~df['ema50_above_200'].shift(1).fillna(False))

    # MACD交叉
    df['macd_above_signal'] = df['macd'] > df['macd_signal']
    df['macd_golden'] = df['macd_above_signal'] & (~df['macd_above_signal'].shift(1).fillna(False))

    # RSI区间
    df['rsi_oversold'] = df['rsi'] < 30
    df['rsi_extreme_oversold'] = df['rsi'] < 20
    df['rsi_overbought'] = df['rsi'] > 70

    # 布林带信号
    df['below_bb_lower'] = df['close'] < df['bb_lower']

    # 成交量信号
    df['volume_spike'] = df['volume_ratio'] > 2.0
    df['volume_climax'] = df['volume_ratio'] > 3.0

    # Pin Bar
    df['bullish_pin'] = (df['lower_wick'] > df['body'] * 2) & (df['upper_wick'] < df['body'])

    # 闪崩信号
    df['flash_crash'] = (df['change_1'] < -5) & (df['total_range'] / df['close'] * 100 > 5)

    # 合并恐惧贪婪指数
    if fg_data is not None:
        fg_daily = fg_data[['timestamp', 'fear_greed']].copy()
        fg_daily['date'] = fg_daily['timestamp'].dt.date
        df['date'] = df['timestamp'].dt.date
        df = df.merge(fg_daily[['date', 'fear_greed']], on='date', how='left')
        df['fear_greed'] = df['fear_greed'].fillna(method='ffill')
        df['extreme_fear'] = df['fear_greed'] <= 15
        df['fear'] = df['fear_greed'] <= 25
        df['greed'] = df['fear_greed'] >= 75
        df['extreme_greed'] = df['fear_greed'] >= 85

    # 合并资金费率
    if funding_data is not None:
        # 简化处理：按日期合并最近的资金费率
        funding_data['date'] = funding_data['timestamp'].dt.date
        daily_funding = funding_data.groupby('date')['fundingRate'].last().reset_index()
        df = df.merge(daily_funding, on='date', how='left')
        df['fundingRate'] = df['fundingRate'].fillna(0)
        df['negative_funding'] = df['fundingRate'] < 0
        df['very_negative_funding'] = df['fundingRate'] < -0.001

    return df


# ==================== 组合策略定义 (向量化版本) ====================

def get_combo_signals(df):
    """预计算所有组合策略的信号 (向量化计算，极大提升性能)"""
    signals = {}

    # 确保默认值存在
    fear = df['fear'].values if 'fear' in df.columns else np.zeros(len(df), dtype=bool)
    extreme_fear = df['extreme_fear'].values if 'extreme_fear' in df.columns else np.zeros(len(df), dtype=bool)
    negative_funding = df['negative_funding'].values if 'negative_funding' in df.columns else np.zeros(len(df), dtype=bool)
    very_negative_funding = df['very_negative_funding'].values if 'very_negative_funding' in df.columns else np.zeros(len(df), dtype=bool)

    # 趋势确认组合
    signals['EMA金叉+上升趋势'] = df['ema7_cross_25'].values & df['uptrend'].values
    signals['EMA金叉+强趋势'] = df['ema7_cross_25'].values & df['strong_uptrend'].values
    signals['EMA金叉+MACD金叉'] = df['ema7_cross_25'].values & df['macd_above_signal'].values
    signals['EMA金叉+放量'] = df['ema7_cross_25'].values & df['volume_spike'].values
    signals['黄金交叉+趋势'] = df['ema50_cross_200'].values & (df['close'].values > df['ema50'].values)

    # 超卖反弹组合
    signals['RSI超卖+恐惧'] = df['rsi_oversold'].values & fear
    signals['RSI极度超卖+极度恐惧'] = df['rsi_extreme_oversold'].values & extreme_fear
    signals['RSI超卖+布林带下轨'] = df['rsi_oversold'].values & df['below_bb_lower'].values
    signals['RSI超卖+大跌'] = df['rsi_oversold'].values & (df['change_7'].values < -15)

    # 恐慌抄底组合
    signals['恐惧+大跌'] = fear & (df['change_7'].values < -10)
    signals['极度恐惧+闪崩'] = extreme_fear & df['flash_crash'].values
    signals['恐惧+Pin Bar'] = fear & df['bullish_pin'].values
    signals['恐惧+放量下跌'] = fear & df['volume_climax'].values & (df['change_1'].values < -3)

    # 技术形态组合
    signals['Pin Bar+上升趋势'] = df['bullish_pin'].values & df['uptrend'].values
    signals['Pin Bar+RSI超卖'] = df['bullish_pin'].values & df['rsi_oversold'].values
    signals['Pin Bar+放量'] = df['bullish_pin'].values & df['volume_spike'].values

    # 多重确认组合
    signals['MACD金叉+RSI回升+趋势'] = (
        df['macd_golden'].values &
        (df['rsi'].values > 30) &
        (df['rsi'].values < 50) &
        df['uptrend'].values
    )
    signals['EMA金叉+MACD金叉+放量'] = (
        df['ema7_cross_25'].values &
        df['macd_above_signal'].values &
        df['volume_spike'].values
    )
    signals['布林带下轨+RSI超卖+恐惧'] = (
        df['below_bb_lower'].values &
        df['rsi_oversold'].values &
        fear
    )

    # 资金费率组合
    signals['负资金费+RSI超卖'] = negative_funding & df['rsi_oversold'].values
    signals['极负资金费+恐惧'] = very_negative_funding & fear

    # 终极组合
    signals['三重底部信号'] = (
        df['rsi_extreme_oversold'].values &
        extreme_fear &
        (df['change_7'].values < -15)
    )
    signals['完美抄底'] = df['rsi_oversold'].values & fear & df['bullish_pin'].values
    signals['趋势+动量+成交量'] = (
        df['ema7_cross_25'].values &
        df['macd_golden'].values &
        df['volume_climax'].values &
        df['uptrend'].values
    )

    return signals


COMBO_DESCRIPTIONS = {
    'EMA金叉+上升趋势': 'EMA7上穿EMA25 且 价格在EMA50上方',
    'EMA金叉+强趋势': 'EMA7上穿EMA25 且 EMA50>EMA200',
    'EMA金叉+MACD金叉': 'EMA7上穿EMA25 且 MACD在信号线上方',
    'EMA金叉+放量': 'EMA7上穿EMA25 且 成交量>2倍均量',
    '黄金交叉+趋势': 'EMA50上穿EMA200 且 价格在EMA50上方',
    'RSI超卖+恐惧': 'RSI<30 且 恐惧贪婪<25',
    'RSI极度超卖+极度恐惧': 'RSI<20 且 恐惧贪婪<15',
    'RSI超卖+布林带下轨': 'RSI<30 且 价格低于布林带下轨',
    'RSI超卖+大跌': 'RSI<30 且 7日跌幅>15%',
    '恐惧+大跌': '恐惧贪婪<25 且 7日跌幅>10%',
    '极度恐惧+闪崩': '恐惧贪婪<15 且 日跌>5%',
    '恐惧+Pin Bar': '恐惧贪婪<25 且 看涨Pin Bar',
    '恐惧+放量下跌': '恐惧贪婪<25 且 放量下跌',
    'Pin Bar+上升趋势': '看涨Pin Bar 且 价格在EMA50上方',
    'Pin Bar+RSI超卖': '看涨Pin Bar 且 RSI<30',
    'Pin Bar+放量': '看涨Pin Bar 且 成交量>2倍均量',
    'MACD金叉+RSI回升+趋势': 'MACD金叉 且 RSI在30-50 且 上升趋势',
    'EMA金叉+MACD金叉+放量': 'EMA金叉+MACD确认+放量',
    '布林带下轨+RSI超卖+恐惧': '布林带下轨+RSI<30+恐惧',
    '负资金费+RSI超卖': '负资金费率 且 RSI<30',
    '极负资金费+恐惧': '资金费率<-0.1% 且 恐惧',
    '三重底部信号': 'RSI<20 + 极度恐惧 + 7日跌>15%',
    '完美抄底': 'RSI<30 + 恐惧 + Pin Bar',
    '趋势+动量+成交量': 'EMA金叉+MACD金叉+放量+趋势',
}


# ==================== 回测引擎 (优化版) ====================

def backtest_with_signal_array(df, signal_array, tp_pct, sl_pct, hold_bars=100, name=""):
    """回测组合策略 - 使用预计算的信号数组 (极快)"""
    trades = []

    # 转换为numpy数组以加速
    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    i = 250  # 跳过预热期

    while i < n - hold_bars:
        if signal_array[i]:
            entry_price = close_arr[i]
            entry_time = timestamps[i]
            tp_price = entry_price * (1 + tp_pct / 100)
            sl_price = entry_price * (1 - sl_pct / 100)

            exit_price, exit_time, exit_reason = None, None, None
            j = i + 1

            # 向量化查找TP/SL
            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                if low_arr[j] <= sl_price:
                    exit_price, exit_time, exit_reason = sl_price, timestamps[j], 'SL'
                    break
                if high_arr[j] >= tp_price:
                    exit_price, exit_time, exit_reason = tp_price, timestamps[j], 'TP'
                    break

            if exit_price is None:
                j = min(i + hold_bars, n - 1)
                exit_price = close_arr[j]
                exit_time = timestamps[j]
                exit_reason = 'TIMEOUT'

            pnl_pct = (exit_price - entry_price) / entry_price * 100

            trades.append({
                'strategy': name,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl_pct': pnl_pct,
            })
            i = j + 1
        else:
            i += 1

    return trades


def calculate_ev(win_rate, tp_pct, sl_pct, leverage=1):
    wr = win_rate / 100
    return (wr * tp_pct * leverage) - ((1 - wr) * sl_pct * leverage)


def optimize_combo_strategy_fast(df, signal_array, name, timeframe):
    """优化组合策略参数 (优化版)"""
    tp_range = [15, 20, 30, 50, 75, 100, 150, 200]
    sl_range = [2, 3, 5, 7, 10, 15]
    lev_range = [5, 10, 15, 20, 25, 30]

    results = []

    for tp in tp_range:
        for sl in sl_range:
            if tp / sl < 2:  # 组合策略要求更高盈亏比
                continue

            trades = backtest_with_signal_array(df, signal_array, tp, sl, hold_bars=100, name=name)

            if len(trades) < 3:  # 至少3笔交易
                continue

            df_t = pd.DataFrame(trades)
            total = len(df_t)
            wins = len(df_t[df_t['pnl_pct'] > 0])
            win_rate = wins / total * 100

            avg_win = df_t[df_t['pnl_pct'] > 0]['pnl_pct'].mean() if wins > 0 else 0
            avg_loss = abs(df_t[df_t['pnl_pct'] <= 0]['pnl_pct'].mean()) if (total - wins) > 0 else 0

            for lev in lev_range:
                if sl * lev >= 90:
                    continue

                ev = calculate_ev(win_rate, tp, sl, lev)

                results.append({
                    'strategy': name,
                    'timeframe': timeframe,
                    'tp': tp,
                    'sl': sl,
                    'leverage': lev,
                    'trades': total,
                    'wins': wins,
                    'win_rate': win_rate,
                    'avg_win': avg_win,
                    'avg_loss': avg_loss,
                    'risk_reward': tp / sl,
                    'ev': ev,
                    'total_pnl': df_t['pnl_pct'].sum() * lev,
                })

    return results


# ==================== 主程序 ====================

def main():
    print("=" * 70)
    print("BTC/USDT 组合策略回测系统 (优化版)")
    print("=" * 70)

    # 加载数据
    data = load_data()

    # 测试时间周期
    timeframes = ['1d', '4h', '1h']

    all_results = []

    for tf in timeframes:
        print(f"\n{'='*50}")
        print(f"回测周期: {tf}")
        print(f"{'='*50}")

        # 添加指标
        df = add_all_indicators(data[tf], data['fear_greed'], data['funding'])

        # 预计算所有信号 (一次性向量化计算)
        signals = get_combo_signals(df)

        for name, signal_arr in signals.items():
            print(f"  - {name}...", end=" ", flush=True)

            try:
                results = optimize_combo_strategy_fast(df, signal_arr, name, tf)

                if results:
                    all_results.extend(results)
                    best = max(results, key=lambda x: x['ev'])
                    print(f"交易:{best['trades']} 胜率:{best['win_rate']:.1f}% EV:{best['ev']:.1f}%")
                else:
                    print("信号不足")
            except Exception as e:
                print(f"错误: {e}")

    # 排序并输出结果
    if all_results:
        all_sorted = sorted(all_results, key=lambda x: x['ev'], reverse=True)

        print("\n" + "=" * 90)
        print("Top 30 最优EV组合策略")
        print("=" * 90)
        print(f"{'排名':<4} {'策略':<25} {'周期':<5} {'TP%':<6} {'SL%':<6} {'杠杆':<5} {'交易':<6} {'胜率':<8} {'EV%':<10}")
        print("-" * 90)

        for i, r in enumerate(all_sorted[:30], 1):
            print(f"{i:<4} {r['strategy']:<25} {r['timeframe']:<5} {r['tp']:<6} {r['sl']:<6} {r['leverage']}x{'':<3} {r['trades']:<6} {r['win_rate']:.1f}%{'':<4} {r['ev']:.1f}%")

        # 保存结果
        df_results = pd.DataFrame(all_sorted)
        df_results.to_csv('../reports/combo_strategy_results.csv', index=False)
        print(f"\n结果已保存: ../reports/combo_strategy_results.csv")

        # 与单策略对比
        print("\n" + "=" * 70)
        print("组合策略胜率排名 (Top 15)")
        print("=" * 70)

        # 按胜率排序
        by_winrate = sorted(all_sorted, key=lambda x: x['win_rate'], reverse=True)[:15]
        print(f"{'策略':<30} {'周期':<5} {'胜率':<10} {'交易数':<8} {'EV%':<10}")
        print("-" * 70)
        for r in by_winrate:
            print(f"{r['strategy']:<30} {r['timeframe']:<5} {r['win_rate']:.1f}%{'':<5} {r['trades']:<8} {r['ev']:.1f}%")

    return all_results


if __name__ == "__main__":
    results = main()
