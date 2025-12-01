#!/usr/bin/env python3
"""
高胜率交易策略 (胜率 > 40%)
基于历史回测筛选
"""

import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
import requests
from datetime import datetime


# 胜率 > 40% 的策略配置 (来自回测结果)
HIGH_WIN_RATE_STRATEGIES = [
    # 周线策略
    {'name': '恐惧+Pin Bar', 'timeframe': '1w', 'win_rate': 100.0, 'ev': 2500, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'RSI超卖+恐惧', 'timeframe': '1w', 'win_rate': 87.5, 'ev': 2178, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'RSI超卖+大跌', 'timeframe': '1w', 'win_rate': 83.3, 'ev': 2071, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+上升趋势', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+强趋势', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'RSI超卖+恐惧', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 225, 'tp': 100, 'sl': 10, 'trail': 0, 'leverage': 5},
    {'name': 'RSI极度超卖+极度恐惧', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 225, 'tp': 100, 'sl': 10, 'trail': 15, 'leverage': 5},
    {'name': '恐惧+大跌', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'Pin Bar+RSI超卖', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '负资金费+RSI超卖', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '三重底部信号', 'timeframe': '1w', 'win_rate': 50.0, 'ev': 225, 'tp': 100, 'sl': 10, 'trail': 15, 'leverage': 5},
    {'name': 'Pin Bar+上升趋势', 'timeframe': '1w', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},

    # 日线策略
    {'name': '黄金交叉+趋势', 'timeframe': '1d', 'win_rate': 50.0, 'ev': 465, 'tp': 100, 'sl': 7, 'trail': 10, 'leverage': 10},
    {'name': '极度恐惧+闪崩', 'timeframe': '1d', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'Pin Bar+RSI超卖', 'timeframe': '1d', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 15, 'leverage': 25},
    {'name': 'MACD金叉+RSI回升+趋势', 'timeframe': '1d', 'win_rate': 50.0, 'ev': 1213, 'tp': 100, 'sl': 3, 'trail': 10, 'leverage': 25},
    {'name': 'Pin Bar+上升趋势', 'timeframe': '1d', 'win_rate': 48.9, 'ev': 1184, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '负资金费+RSI超卖', 'timeframe': '1d', 'win_rate': 43.5, 'ev': 1045, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '布林带下轨+RSI超卖+恐惧', 'timeframe': '1d', 'win_rate': 42.9, 'ev': 1029, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+强趋势', 'timeframe': '1d', 'win_rate': 41.7, 'ev': 998, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'RSI超卖+布林带下轨', 'timeframe': '1d', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},

    # 4小时策略
    {'name': '趋势+动量+成交量', 'timeframe': '4h', 'win_rate': 60.0, 'ev': 1470, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '黄金交叉+趋势', 'timeframe': '4h', 'win_rate': 51.6, 'ev': 1254, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+MACD金叉+放量', 'timeframe': '4h', 'win_rate': 51.4, 'ev': 1249, 'tp': 100, 'sl': 3, 'trail': 10, 'leverage': 25},
    {'name': '极度恐惧+闪崩', 'timeframe': '4h', 'win_rate': 50.0, 'ev': 225, 'tp': 100, 'sl': 10, 'trail': 0, 'leverage': 5},
    {'name': '完美抄底', 'timeframe': '4h', 'win_rate': 47.8, 'ev': 1157, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+放量', 'timeframe': '4h', 'win_rate': 47.6, 'ev': 1151, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'RSI超卖+大跌', 'timeframe': '4h', 'win_rate': 46.2, 'ev': 1113, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': 'EMA金叉+MACD金叉+放量', 'timeframe': '4h', 'win_rate': 44.1, 'ev': 1061, 'tp': 100, 'sl': 3, 'trail': 0, 'leverage': 25},
    {'name': 'EMA金叉+放量', 'timeframe': '4h', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 0, 'leverage': 25},
    {'name': '三重底部信号', 'timeframe': '4h', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},

    # 1小时策略
    {'name': '极度恐惧+闪崩', 'timeframe': '1h', 'win_rate': 75.0, 'ev': 1856, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '恐惧+放量下跌', 'timeframe': '1h', 'win_rate': 47.6, 'ev': 675, 'tp': 100, 'sl': 5, 'trail': 0, 'leverage': 15},
    {'name': '趋势+动量+成交量', 'timeframe': '1h', 'win_rate': 47.1, 'ev': 1137, 'tp': 100, 'sl': 3, 'trail': 10, 'leverage': 25},
    {'name': '黄金交叉+趋势', 'timeframe': '1h', 'win_rate': 44.4, 'ev': 1068, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '趋势+动量+成交量', 'timeframe': '1h', 'win_rate': 44.1, 'ev': 1061, 'tp': 100, 'sl': 3, 'trail': 0, 'leverage': 25},
    {'name': '负资金费+RSI超卖', 'timeframe': '1h', 'win_rate': 43.5, 'ev': 1046, 'tp': 100, 'sl': 3, 'trail': 0, 'leverage': 25},
    {'name': '黄金交叉+趋势', 'timeframe': '1h', 'win_rate': 43.0, 'ev': 1033, 'tp': 100, 'sl': 3, 'trail': 0, 'leverage': 25},
    {'name': '恐惧+大跌', 'timeframe': '1h', 'win_rate': 42.9, 'ev': 1029, 'tp': 100, 'sl': 3, 'trail': 10, 'leverage': 25},
    {'name': '极度恐惧+闪崩', 'timeframe': '1h', 'win_rate': 40.0, 'ev': 170, 'tp': 100, 'sl': 10, 'trail': 0, 'leverage': 5},
    {'name': 'RSI超卖+大跌', 'timeframe': '1h', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
    {'name': '三重底部信号', 'timeframe': '1h', 'win_rate': 40.0, 'ev': 955, 'tp': 100, 'sl': 3, 'trail': 5, 'leverage': 25},
]


def get_fear_greed_index() -> Tuple[float, str]:
    """获取恐惧贪婪指数"""
    try:
        response = requests.get(
            'https://api.alternative.me/fng/?limit=1',
            timeout=10
        )
        data = response.json()
        value = float(data['data'][0]['value'])
        classification = data['data'][0]['value_classification']
        return value, classification
    except Exception:
        return 50.0, 'Neutral'


def calculate_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """计算所有技术指标"""
    df = df.copy()

    # EMA
    df['ema12'] = df['close'].ewm(span=12).mean()
    df['ema26'] = df['close'].ewm(span=26).mean()
    df['ema50'] = df['close'].ewm(span=50).mean()
    df['ema200'] = df['close'].ewm(span=200).mean()

    # MACD
    df['macd'] = df['ema12'] - df['ema26']
    df['macd_signal'] = df['macd'].ewm(span=9).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # RSI
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    # 布林带
    df['bb_mid'] = df['close'].rolling(window=20).mean()
    df['bb_std'] = df['close'].rolling(window=20).std()
    df['bb_upper'] = df['bb_mid'] + 2 * df['bb_std']
    df['bb_lower'] = df['bb_mid'] - 2 * df['bb_std']

    # 成交量MA
    df['volume_ma'] = df['volume'].rolling(window=20).mean()
    df['volume_ratio'] = df['volume'] / df['volume_ma']

    # ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    df['atr'] = tr.rolling(window=14).mean()

    # 价格变化
    df['pct_change'] = df['close'].pct_change() * 100
    df['pct_change_5'] = df['close'].pct_change(5) * 100

    # Pin Bar检测
    body = abs(df['close'] - df['open'])
    upper_wick = df['high'] - df[['close', 'open']].max(axis=1)
    lower_wick = df[['close', 'open']].min(axis=1) - df['low']
    candle_range = df['high'] - df['low']

    df['is_pin_bar'] = (
        (lower_wick > body * 2) &
        (lower_wick > upper_wick * 2) &
        (candle_range > 0)
    )

    return df


def check_strategy_signal(df: pd.DataFrame, strategy_name: str, fear_index: float) -> bool:
    """
    检查策略信号是否触发

    参数:
        df: K线数据 (需要已计算指标)
        strategy_name: 策略名称
        fear_index: 恐惧贪婪指数 (0-100)

    返回:
        是否触发买入信号
    """
    if len(df) < 2:
        return False

    # 获取最新K线数据
    curr = df.iloc[-1]
    prev = df.iloc[-2]

    # 基础条件
    ema_golden_cross = prev['ema12'] <= prev['ema26'] and curr['ema12'] > curr['ema26']
    macd_golden_cross = prev['macd'] <= prev['macd_signal'] and curr['macd'] > curr['macd_signal']
    rsi_oversold = curr['rsi'] < 30
    rsi_extreme_oversold = curr['rsi'] < 20
    rsi_rising = curr['rsi'] > prev['rsi']
    price_below_bb = curr['close'] < curr['bb_lower']
    uptrend = curr['ema50'] > curr['ema200']
    strong_uptrend = curr['close'] > curr['ema50'] > curr['ema200']
    volume_surge = curr['volume_ratio'] > 1.5
    big_drop = curr['pct_change'] < -5
    flash_crash = curr['pct_change'] < -10
    is_pin_bar = curr['is_pin_bar']

    fear = fear_index < 30
    extreme_fear = fear_index < 20

    # 策略条件判断
    signals = {
        'EMA金叉+上升趋势': ema_golden_cross and uptrend,
        'EMA金叉+强趋势': ema_golden_cross and strong_uptrend,
        'EMA金叉+MACD金叉': ema_golden_cross and macd_golden_cross,
        'EMA金叉+放量': ema_golden_cross and volume_surge,
        '黄金交叉+趋势': (prev['ema50'] <= prev['ema200'] and curr['ema50'] > curr['ema200']),
        'RSI超卖+恐惧': rsi_oversold and fear,
        'RSI极度超卖+极度恐惧': rsi_extreme_oversold and extreme_fear,
        'RSI超卖+布林带下轨': rsi_oversold and price_below_bb,
        'RSI超卖+大跌': rsi_oversold and big_drop,
        '恐惧+大跌': fear and big_drop,
        '极度恐惧+闪崩': extreme_fear and flash_crash,
        '恐惧+Pin Bar': fear and is_pin_bar,
        '恐惧+放量下跌': fear and volume_surge and curr['pct_change'] < 0,
        'Pin Bar+上升趋势': is_pin_bar and uptrend,
        'Pin Bar+RSI超卖': is_pin_bar and rsi_oversold,
        'Pin Bar+放量': is_pin_bar and volume_surge,
        'MACD金叉+RSI回升+趋势': macd_golden_cross and rsi_rising and uptrend,
        'EMA金叉+MACD金叉+放量': ema_golden_cross and macd_golden_cross and volume_surge,
        '布林带下轨+RSI超卖+恐惧': price_below_bb and rsi_oversold and fear,
        '负资金费+RSI超卖': rsi_oversold,  # 简化版，实际需要资金费率数据
        '三重底部信号': rsi_extreme_oversold and extreme_fear and price_below_bb,
        '完美抄底': rsi_extreme_oversold and extreme_fear and is_pin_bar,
        '趋势+动量+成交量': uptrend and macd_golden_cross and volume_surge,
    }

    return signals.get(strategy_name, False)


def get_triggered_strategies(df: pd.DataFrame, fear_index: float, timeframe: str) -> List[Dict]:
    """
    获取当前触发的所有策略

    参数:
        df: K线数据
        fear_index: 恐惧贪婪指数
        timeframe: 时间周期 (1h, 4h, 1d, 1w)

    返回:
        触发的策略列表
    """
    # 计算指标
    df = calculate_indicators(df)

    triggered = []
    for strategy in HIGH_WIN_RATE_STRATEGIES:
        if strategy['timeframe'] != timeframe:
            continue

        if check_strategy_signal(df, strategy['name'], fear_index):
            triggered.append(strategy)

    # 按胜率排序
    triggered.sort(key=lambda x: x['win_rate'], reverse=True)
    return triggered


def get_strategies_by_timeframe(timeframe: str) -> List[Dict]:
    """获取指定周期的所有策略"""
    return [s for s in HIGH_WIN_RATE_STRATEGIES if s['timeframe'] == timeframe]


def get_all_strategies() -> List[Dict]:
    """获取所有策略"""
    return HIGH_WIN_RATE_STRATEGIES.copy()
