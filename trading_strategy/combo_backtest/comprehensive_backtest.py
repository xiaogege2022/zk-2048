#!/usr/bin/env python3
"""
BTC/USDT 全面组合策略回测系统
- 覆盖所有时间周期: 1w, 1d, 4h, 1h
- 包含固定止盈止损和移动止盈止损
- 详细统计每个策略的表现
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

# ==================== 数据加载 ====================

def load_data():
    """加载所有数据"""
    print("加载数据...")

    data = {}

    # K线数据 - 包含周线
    timeframes = [
        ('1w', 'BTCUSDT_1w.csv'),
        ('1d', 'BTCUSDT_1d.csv'),
        ('4h', 'BTCUSDT_4h.csv'),
        ('1h', 'BTCUSDT_1h.csv'),
    ]

    for tf, file in timeframes:
        try:
            df = pd.read_csv(file)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            data[tf] = df
            print(f"  {tf}: {len(df):,} K线")
        except Exception as e:
            print(f"  {tf}: 加载失败 - {e}")

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
        df['fear_greed'] = df['fear_greed'].ffill()
        df['extreme_fear'] = df['fear_greed'] <= 15
        df['fear'] = df['fear_greed'] <= 25
        df['greed'] = df['fear_greed'] >= 75
        df['extreme_greed'] = df['fear_greed'] >= 85

    # 合并资金费率
    if funding_data is not None:
        funding_data = funding_data.copy()
        funding_data['date'] = funding_data['timestamp'].dt.date
        daily_funding = funding_data.groupby('date')['fundingRate'].last().reset_index()
        df = df.merge(daily_funding, on='date', how='left')
        df['fundingRate'] = df['fundingRate'].fillna(0)
        df['negative_funding'] = df['fundingRate'] < 0
        df['very_negative_funding'] = df['fundingRate'] < -0.001

    return df


# ==================== 组合策略定义 ====================

def get_combo_signals(df):
    """预计算所有组合策略的信号"""
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


# 策略说明 - 所有EMA/RSI/MACD等指标均基于当前K线周期计算(周线策略用周线指标,日线策略用日线指标,以此类推)
STRATEGY_DESCRIPTIONS = {
    'EMA金叉+上升趋势': '【当前周期】EMA7上穿EMA25(本根K线EMA7>EMA25且前一根EMA7<EMA25) 且 收盘价>EMA50',
    'EMA金叉+强趋势': '【当前周期】EMA7上穿EMA25 且 收盘价>EMA50 且 EMA50>EMA200',
    'EMA金叉+MACD金叉': '【当前周期】EMA7上穿EMA25 且 MACD(12,26,9)线>信号线',
    'EMA金叉+放量': '【当前周期】EMA7上穿EMA25 且 成交量>20周期均量×2',
    '黄金交叉+趋势': '【当前周期】EMA50上穿EMA200(本根K线EMA50>EMA200且前一根EMA50<EMA200) 且 收盘价>EMA50',
    'RSI超卖+恐惧': '【当前周期】RSI(14)<30 且 恐惧贪婪指数≤25',
    'RSI极度超卖+极度恐惧': '【当前周期】RSI(14)<20 且 恐惧贪婪指数≤15',
    'RSI超卖+布林带下轨': '【当前周期】RSI(14)<30 且 收盘价<布林带下轨(20周期,2倍标准差)',
    'RSI超卖+大跌': '【当前周期】RSI(14)<30 且 7根K线跌幅>15%',
    '恐惧+大跌': '恐惧贪婪指数≤25 且 【当前周期】7根K线跌幅>10%',
    '极度恐惧+闪崩': '恐惧贪婪指数≤15 且 【当前周期】当根K线跌幅>5% 且 振幅(最高-最低)/收盘价>5%',
    '恐惧+Pin Bar': '恐惧贪婪指数≤25 且 【当前周期】看涨Pin Bar(下影线>实体×2 且 上影线<实体)',
    '恐惧+放量下跌': '恐惧贪婪指数≤25 且 【当前周期】成交量>20周期均量×3 且 当根K线跌幅>3%',
    'Pin Bar+上升趋势': '【当前周期】看涨Pin Bar(下影线>实体×2 且 上影线<实体) 且 收盘价>EMA50',
    'Pin Bar+RSI超卖': '【当前周期】看涨Pin Bar(下影线>实体×2 且 上影线<实体) 且 RSI(14)<30',
    'Pin Bar+放量': '【当前周期】看涨Pin Bar(下影线>实体×2 且 上影线<实体) 且 成交量>20周期均量×2',
    'MACD金叉+RSI回升+趋势': '【当前周期】MACD(12,26,9)金叉(本根MACD>信号线且前一根MACD<信号线) 且 30<RSI(14)<50 且 收盘价>EMA50',
    'EMA金叉+MACD金叉+放量': '【当前周期】EMA7上穿EMA25 且 MACD线>信号线 且 成交量>20周期均量×2',
    '布林带下轨+RSI超卖+恐惧': '【当前周期】收盘价<布林带下轨(20周期,2倍标准差) 且 RSI(14)<30 且 恐惧贪婪指数≤25',
    '负资金费+RSI超卖': '资金费率<0(任何负值) 且 【当前周期】RSI(14)<30',
    '极负资金费+恐惧': '资金费率<-0.1%(-0.001) 且 恐惧贪婪指数≤25',
    '三重底部信号': '【当前周期】RSI(14)<20 且 恐惧贪婪指数≤15 且 7根K线跌幅>15%',
    '完美抄底': '【当前周期】RSI(14)<30 且 恐惧贪婪指数≤25 且 看涨Pin Bar(下影线>实体×2 且 上影线<实体)',
    '趋势+动量+成交量': '【当前周期】EMA7上穿EMA25 且 MACD金叉 且 成交量>20周期均量×3 且 收盘价>EMA50',
}


# ==================== 回测引擎 ====================

def backtest_fixed_tpsl(df, signal_array, tp_pct, sl_pct, hold_bars=100, name=""):
    """固定止盈止损回测"""
    trades = []

    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    warmup = min(250, n // 4)  # 动态预热期
    i = warmup

    while i < n - hold_bars:
        if signal_array[i]:
            entry_price = close_arr[i]
            entry_time = timestamps[i]
            tp_price = entry_price * (1 + tp_pct / 100)
            sl_price = entry_price * (1 - sl_pct / 100)

            exit_price, exit_time, exit_reason = None, None, None

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
                'tp_type': 'fixed',
            })
            i = j + 1
        else:
            i += 1

    return trades


def backtest_trailing_stop(df, signal_array, tp_pct, sl_pct, trail_pct, hold_bars=100, name=""):
    """移动止盈止损回测"""
    trades = []

    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    warmup = min(250, n // 4)
    i = warmup

    while i < n - hold_bars:
        if signal_array[i]:
            entry_price = close_arr[i]
            entry_time = timestamps[i]
            tp_price = entry_price * (1 + tp_pct / 100)
            sl_price = entry_price * (1 - sl_pct / 100)
            highest_price = entry_price

            exit_price, exit_time, exit_reason = None, None, None

            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                # 更新最高价和移动止损
                if high_arr[j] > highest_price:
                    highest_price = high_arr[j]
                    # 移动止损：最高价回撤trail_pct%
                    trail_stop = highest_price * (1 - trail_pct / 100)
                    if trail_stop > sl_price:
                        sl_price = trail_stop

                # 检查止损
                if low_arr[j] <= sl_price:
                    exit_price = sl_price
                    exit_time = timestamps[j]
                    exit_reason = 'TRAIL_SL' if sl_price > entry_price * (1 - sl_pct / 100) else 'SL'
                    break

                # 检查止盈
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
                'tp_type': 'trailing',
            })
            i = j + 1
        else:
            i += 1

    return trades


def calculate_ev(win_rate, tp_pct, sl_pct, leverage=1):
    wr = win_rate / 100
    return (wr * tp_pct * leverage) - ((1 - wr) * sl_pct * leverage)


def analyze_strategy(df, signal_array, name, timeframe):
    """全面分析单个策略"""
    results = []

    # 止盈止损参数范围
    tp_range = [10, 15, 20, 30, 50, 75, 100, 150, 200]
    sl_range = [1, 2, 3, 5, 7, 10, 15, 20]
    lev_range = [5, 10, 15, 20, 25, 30]
    trail_range = [5, 10, 15, 20]

    # 1. 固定止盈止损
    for tp in tp_range:
        for sl in sl_range:
            if tp / sl < 1.5:  # 至少1.5:1盈亏比
                continue

            trades = backtest_fixed_tpsl(df, signal_array, tp, sl, hold_bars=100, name=name)

            if len(trades) >= 2:  # 放宽到至少2笔交易
                df_t = pd.DataFrame(trades)
                total = len(df_t)
                wins = len(df_t[df_t['pnl_pct'] > 0])
                win_rate = wins / total * 100

                for lev in lev_range:
                    if sl * lev >= 90:
                        continue

                    ev = calculate_ev(win_rate, tp, sl, lev)

                    results.append({
                        'strategy': name,
                        'timeframe': timeframe,
                        'tp_type': 'fixed',
                        'tp': tp,
                        'sl': sl,
                        'trail': 0,
                        'leverage': lev,
                        'trades': total,
                        'wins': wins,
                        'win_rate': win_rate,
                        'risk_reward': tp / sl,
                        'ev': ev,
                    })

    # 2. 移动止盈止损
    for tp in tp_range:
        for sl in sl_range:
            for trail in trail_range:
                if tp / sl < 1.5:
                    continue

                trades = backtest_trailing_stop(df, signal_array, tp, sl, trail, hold_bars=100, name=name)

                if len(trades) >= 2:
                    df_t = pd.DataFrame(trades)
                    total = len(df_t)
                    wins = len(df_t[df_t['pnl_pct'] > 0])
                    win_rate = wins / total * 100

                    for lev in lev_range:
                        if sl * lev >= 90:
                            continue

                        ev = calculate_ev(win_rate, tp, sl, lev)

                        results.append({
                            'strategy': name,
                            'timeframe': timeframe,
                            'tp_type': 'trailing',
                            'tp': tp,
                            'sl': sl,
                            'trail': trail,
                            'leverage': lev,
                            'trades': total,
                            'wins': wins,
                            'win_rate': win_rate,
                            'risk_reward': tp / sl,
                            'ev': ev,
                        })

    return results


# ==================== 主程序 ====================

def main():
    print("=" * 80)
    print("BTC/USDT 全面组合策略回测系统")
    print("包含: 1w, 1d, 4h, 1h | 固定止盈止损 + 移动止盈止损")
    print("=" * 80)

    # 加载数据
    data = load_data()

    # 所有时间周期
    timeframes = ['1w', '1d', '4h', '1h']

    all_results = []
    strategy_stats = {}  # 统计每个策略在各周期的信号数

    for tf in timeframes:
        if tf not in data:
            print(f"\n跳过 {tf} - 数据不可用")
            continue

        print(f"\n{'='*60}")
        print(f"回测周期: {tf}")
        print(f"{'='*60}")

        # 添加指标
        df = add_all_indicators(data[tf], data['fear_greed'], data['funding'])

        # 预计算所有信号
        signals = get_combo_signals(df)

        for name, signal_arr in signals.items():
            signal_count = np.sum(signal_arr)

            # 记录统计
            if name not in strategy_stats:
                strategy_stats[name] = {}
            strategy_stats[name][tf] = signal_count

            print(f"  - {name}... 信号:{signal_count}", end=" ")

            if signal_count < 2:
                print("(信号不足)")
                continue

            try:
                results = analyze_strategy(df, signal_arr, name, tf)

                if results:
                    all_results.extend(results)
                    best = max(results, key=lambda x: x['ev'])
                    print(f"交易:{best['trades']} 胜率:{best['win_rate']:.1f}% EV:{best['ev']:.1f}%")
                else:
                    print("(无有效参数组合)")
            except Exception as e:
                print(f"错误: {e}")

    # 保存结果
    if all_results:
        df_results = pd.DataFrame(all_results)
        df_results.to_csv('../reports/comprehensive_results.csv', index=False)

        # 生成详细报告
        generate_report(df_results, strategy_stats)

    return all_results, strategy_stats


def generate_report(df, strategy_stats):
    """生成HTML报告"""

    # 按EV排序
    top_ev = df.sort_values('ev', ascending=False).head(50)

    # 按胜率排序
    top_winrate = df.sort_values('win_rate', ascending=False).head(50)

    # 按时间周期分组的最佳策略
    best_by_tf = {}
    for tf in ['1w', '1d', '4h', '1h']:
        tf_data = df[df['timeframe'] == tf]
        if len(tf_data) > 0:
            best_by_tf[tf] = tf_data.sort_values('ev', ascending=False).head(10)

    # 每个策略的最佳参数
    best_by_strategy = df.loc[df.groupby('strategy')['ev'].idxmax()]

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 全面策略分析报告</title>
    <style>
        body {{
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #1a1a2e, #16213e, #0f3460);
            color: #e0e0e0;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1600px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            color: #ffd700;
            font-size: 2.5em;
            text-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
        }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
        .section {{
            background: rgba(255,255,255,0.03);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 25px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .section h2 {{
            color: #ffd700;
            border-bottom: 2px solid #ffd700;
            padding-bottom: 10px;
            margin-top: 0;
        }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.9em; }}
        th {{
            background: rgba(255, 215, 0, 0.2);
            color: #ffd700;
            padding: 12px 6px;
            text-align: left;
        }}
        td {{ padding: 10px 6px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        tr:hover {{ background: rgba(255,215,0,0.05); }}
        .ev-super {{ color: #ffd700; font-weight: bold; }}
        .ev-high {{ color: #4ade80; font-weight: bold; }}
        .winrate-super {{ color: #ffd700; font-weight: bold; }}
        .winrate-high {{ color: #4ade80; }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 8px;
            font-size: 0.75em;
            font-weight: bold;
        }}
        .badge-1w {{ background: #dc2626; }}
        .badge-1d {{ background: #ea580c; }}
        .badge-4h {{ background: #2563eb; }}
        .badge-1h {{ background: #7c3aed; }}
        .badge-fixed {{ background: #059669; }}
        .badge-trail {{ background: #0891b2; }}
        .highlight {{ background: linear-gradient(90deg, rgba(255,215,0,0.1), transparent); }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin-bottom: 25px;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.05);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
        }}
        .stat-value {{ font-size: 2em; color: #ffd700; font-weight: bold; }}
        .stat-label {{ color: #888; margin-top: 5px; }}
        .signal-table {{ font-size: 0.85em; }}
        .signal-zero {{ color: #666; }}
        .signal-low {{ color: #f97316; }}
        .signal-ok {{ color: #4ade80; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 全面策略分析报告</h1>
        <p class="subtitle">覆盖周期: 1w, 1d, 4h, 1h | 止盈止损: 固定 + 移动 | 生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

        <!-- 统计概览 -->
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(df):,}</div>
                <div class="stat-label">参数组合总数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{df['ev'].max():.1f}%</div>
                <div class="stat-label">最高EV</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{df['win_rate'].max():.1f}%</div>
                <div class="stat-label">最高胜率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(df['strategy'].unique())}</div>
                <div class="stat-label">策略数量</div>
            </div>
        </div>

        <!-- 策略信号统计 -->
        <div class="section">
            <h2>各策略信号数量统计</h2>
            <table class="signal-table">
                <tr>
                    <th>策略名称</th>
                    <th>条件描述</th>
                    <th>1w信号</th>
                    <th>1d信号</th>
                    <th>4h信号</th>
                    <th>1h信号</th>
                </tr>
"""

    for name, desc in STRATEGY_DESCRIPTIONS.items():
        stats = strategy_stats.get(name, {})
        w = stats.get('1w', 0)
        d = stats.get('1d', 0)
        h4 = stats.get('4h', 0)
        h1 = stats.get('1h', 0)

        def get_class(v):
            if v == 0:
                return 'signal-zero'
            elif v < 5:
                return 'signal-low'
            return 'signal-ok'

        html += f"""
                <tr>
                    <td><b>{name}</b></td>
                    <td>{desc}</td>
                    <td class="{get_class(w)}">{w}</td>
                    <td class="{get_class(d)}">{d}</td>
                    <td class="{get_class(h4)}">{h4}</td>
                    <td class="{get_class(h1)}">{h1}</td>
                </tr>"""

    html += """
            </table>
        </div>

        <!-- Top 50 EV策略 -->
        <div class="section">
            <h2>Top 50 最优EV策略 (所有周期)</h2>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>周期</th>
                    <th>止盈类型</th>
                    <th>TP%</th>
                    <th>SL%</th>
                    <th>移动%</th>
                    <th>杠杆</th>
                    <th>交易</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""

    for i, (_, row) in enumerate(top_ev.iterrows(), 1):
        tf_class = f"badge-{row['timeframe']}"
        tp_class = "badge-trail" if row['tp_type'] == 'trailing' else "badge-fixed"
        ev_class = 'ev-super' if row['ev'] > 2000 else 'ev-high' if row['ev'] > 1000 else ''
        wr_class = 'winrate-super' if row['win_rate'] >= 50 else 'winrate-high' if row['win_rate'] >= 40 else ''
        highlight = 'highlight' if i <= 5 else ''

        html += f"""
                <tr class="{highlight}">
                    <td>{i}</td>
                    <td>{row['strategy']}</td>
                    <td><span class="badge {tf_class}">{row['timeframe']}</span></td>
                    <td><span class="badge {tp_class}">{row['tp_type']}</span></td>
                    <td>{row['tp']}%</td>
                    <td>{row['sl']}%</td>
                    <td>{row['trail']}%</td>
                    <td>{row['leverage']}x</td>
                    <td>{row['trades']}</td>
                    <td class="{wr_class}">{row['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{row['ev']:.1f}%</td>
                </tr>"""

    html += """
            </table>
        </div>
"""

    # 各周期最佳策略
    for tf in ['1w', '1d', '4h', '1h']:
        if tf in best_by_tf:
            tf_name = {'1w': '周线', '1d': '日线', '4h': '4小时', '1h': '1小时'}[tf]
            html += f"""
        <div class="section">
            <h2>{tf_name} ({tf}) Top 10 策略</h2>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>止盈类型</th>
                    <th>TP%</th>
                    <th>SL%</th>
                    <th>移动%</th>
                    <th>杠杆</th>
                    <th>交易</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""
            for i, (_, row) in enumerate(best_by_tf[tf].iterrows(), 1):
                tp_class = "badge-trail" if row['tp_type'] == 'trailing' else "badge-fixed"
                ev_class = 'ev-super' if row['ev'] > 1000 else 'ev-high' if row['ev'] > 500 else ''

                html += f"""
                <tr>
                    <td>{i}</td>
                    <td>{row['strategy']}</td>
                    <td><span class="badge {tp_class}">{row['tp_type']}</span></td>
                    <td>{row['tp']}%</td>
                    <td>{row['sl']}%</td>
                    <td>{row['trail']}%</td>
                    <td>{row['leverage']}x</td>
                    <td>{row['trades']}</td>
                    <td>{row['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{row['ev']:.1f}%</td>
                </tr>"""

            html += """
            </table>
        </div>
"""

    # 每个策略的最佳参数
    html += """
        <div class="section">
            <h2>每个策略的最佳参数配置</h2>
            <table>
                <tr>
                    <th>策略</th>
                    <th>最佳周期</th>
                    <th>止盈类型</th>
                    <th>TP%</th>
                    <th>SL%</th>
                    <th>移动%</th>
                    <th>杠杆</th>
                    <th>交易</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""

    for _, row in best_by_strategy.sort_values('ev', ascending=False).iterrows():
        tf_class = f"badge-{row['timeframe']}"
        tp_class = "badge-trail" if row['tp_type'] == 'trailing' else "badge-fixed"
        ev_class = 'ev-super' if row['ev'] > 1000 else 'ev-high' if row['ev'] > 500 else ''

        html += f"""
                <tr>
                    <td><b>{row['strategy']}</b></td>
                    <td><span class="badge {tf_class}">{row['timeframe']}</span></td>
                    <td><span class="badge {tp_class}">{row['tp_type']}</span></td>
                    <td>{row['tp']}%</td>
                    <td>{row['sl']}%</td>
                    <td>{row['trail']}%</td>
                    <td>{row['leverage']}x</td>
                    <td>{row['trades']}</td>
                    <td>{row['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{row['ev']:.1f}%</td>
                </tr>"""

    html += """
            </table>
        </div>

        <div style="text-align: center; color: #666; margin-top: 30px; padding: 20px;">
            <p>EV公式: E(R) = (胜率 × 止盈% × 杠杆) - ((1-胜率) × 止损% × 杠杆)</p>
            <p>数据来源: Binance BTCUSDT 期货 | 2019-09 至 2025-11</p>
        </div>
    </div>
</body>
</html>
"""

    with open('../reports/全面策略分析报告.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告已保存: ../reports/全面策略分析报告.html")


if __name__ == "__main__":
    results, stats = main()
