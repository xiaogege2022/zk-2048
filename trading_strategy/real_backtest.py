#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC/USDT 真实历史数据回测系统
使用币安历史K线数据验证最优止盈止损参数
"""

import json
import urllib.request
import urllib.parse
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional
import time

# ============================================
# 币安API获取历史K线数据
# ============================================

def fetch_binance_klines(symbol: str = "BTCUSDT", interval: str = "1h",
                         limit: int = 1000, start_time: int = None) -> List[Dict]:
    """
    从币安获取历史K线数据

    interval: 1m, 5m, 15m, 1h, 4h, 1d
    """
    base_url = "https://api.binance.com/api/v3/klines"
    params = {
        "symbol": symbol,
        "interval": interval,
        "limit": limit
    }
    if start_time:
        params["startTime"] = start_time

    url = f"{base_url}?{urllib.parse.urlencode(params)}"

    try:
        req = urllib.request.Request(url, headers={
            'User-Agent': 'Mozilla/5.0'
        })
        with urllib.request.urlopen(req, timeout=30) as response:
            data = json.loads(response.read().decode())

        klines = []
        for k in data:
            klines.append({
                "timestamp": k[0],
                "open": float(k[1]),
                "high": float(k[2]),
                "low": float(k[3]),
                "close": float(k[4]),
                "volume": float(k[5]),
                "close_time": k[6],
                "datetime": datetime.fromtimestamp(k[0] / 1000).strftime("%Y-%m-%d %H:%M")
            })
        return klines
    except Exception as e:
        print(f"获取K线数据失败: {e}")
        return []


def fetch_all_historical_data(symbol: str = "BTCUSDT", interval: str = "1h",
                               days: int = 365) -> List[Dict]:
    """
    获取多天历史数据（分批获取）
    """
    all_klines = []
    end_time = int(datetime.now().timestamp() * 1000)
    start_time = int((datetime.now() - timedelta(days=days)).timestamp() * 1000)

    current_start = start_time
    batch_size = 1000  # 币安单次最多1000条

    print(f"正在获取 {days} 天历史数据...")

    while current_start < end_time:
        klines = fetch_binance_klines(symbol, interval, batch_size, current_start)
        if not klines:
            break

        all_klines.extend(klines)
        current_start = klines[-1]["close_time"] + 1

        print(f"  已获取 {len(all_klines)} 条K线数据...")
        time.sleep(0.2)  # 避免请求过快

    print(f"✅ 共获取 {len(all_klines)} 条K线数据")
    return all_klines


# ============================================
# 技术指标计算
# ============================================

def calculate_ema(prices: List[float], period: int) -> List[float]:
    """计算EMA"""
    if len(prices) < period:
        return [0] * len(prices)

    ema = []
    multiplier = 2 / (period + 1)

    # 第一个EMA使用SMA
    sma = sum(prices[:period]) / period
    ema.extend([0] * (period - 1))
    ema.append(sma)

    for i in range(period, len(prices)):
        new_ema = (prices[i] - ema[-1]) * multiplier + ema[-1]
        ema.append(new_ema)

    return ema


def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
    """计算RSI"""
    if len(prices) < period + 1:
        return [50] * len(prices)

    rsi = [50] * period
    gains = []
    losses = []

    for i in range(1, len(prices)):
        change = prices[i] - prices[i-1]
        gains.append(max(0, change))
        losses.append(max(0, -change))

    for i in range(period, len(prices)):
        avg_gain = sum(gains[i-period:i]) / period
        avg_loss = sum(losses[i-period:i]) / period

        if avg_loss == 0:
            rsi.append(100)
        else:
            rs = avg_gain / avg_loss
            rsi.append(100 - (100 / (1 + rs)))

    return rsi


def calculate_macd(prices: List[float], fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[List[float], List[float], List[float]]:
    """计算MACD"""
    ema_fast = calculate_ema(prices, fast)
    ema_slow = calculate_ema(prices, slow)

    macd_line = [f - s for f, s in zip(ema_fast, ema_slow)]
    signal_line = calculate_ema(macd_line, signal)
    histogram = [m - s for m, s in zip(macd_line, signal_line)]

    return macd_line, signal_line, histogram


# ============================================
# 策略信号检测
# ============================================

def detect_ema_crossover(klines: List[Dict], fast: int = 7, slow: int = 25) -> List[Dict]:
    """
    检测EMA金叉信号
    返回所有金叉点及后续价格走势
    """
    closes = [k["close"] for k in klines]
    ema_fast = calculate_ema(closes, fast)
    ema_slow = calculate_ema(closes, slow)

    signals = []

    for i in range(slow + 1, len(klines)):
        # 金叉: 快线从下穿上慢线
        if ema_fast[i-1] <= ema_slow[i-1] and ema_fast[i] > ema_slow[i]:
            entry_price = klines[i]["close"]
            entry_time = klines[i]["datetime"]

            # 计算后续最大涨幅和最大跌幅(接下来24根K线)
            max_gain = 0
            max_loss = 0
            final_return = 0

            for j in range(i+1, min(i+25, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            if i + 24 < len(klines):
                final_return = (klines[i+24]["close"] - entry_price) / entry_price * 100

            signals.append({
                "type": f"EMA{fast}/{slow}金叉",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "final_return": final_return,
                "index": i
            })

    return signals


def detect_trend_ema_crossover(klines: List[Dict]) -> List[Dict]:
    """
    检测趋势中EMA金叉 (价格在EMA50上方时的EMA7/25金叉)
    """
    closes = [k["close"] for k in klines]
    ema7 = calculate_ema(closes, 7)
    ema25 = calculate_ema(closes, 25)
    ema50 = calculate_ema(closes, 50)

    signals = []

    for i in range(51, len(klines)):
        # 条件: 金叉 + 价格在EMA50上方
        if (ema7[i-1] <= ema25[i-1] and ema7[i] > ema25[i] and
            klines[i]["close"] > ema50[i]):

            entry_price = klines[i]["close"]
            entry_time = klines[i]["datetime"]

            max_gain = 0
            max_loss = 0

            for j in range(i+1, min(i+49, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            signals.append({
                "type": "趋势EMA交叉",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "index": i
            })

    return signals


def detect_pin_bar(klines: List[Dict]) -> List[Dict]:
    """
    检测看涨插针(锤子线)形态
    下影线 > 实体的2倍, 上影线很小
    """
    signals = []

    for i in range(1, len(klines)):
        k = klines[i]
        body = abs(k["close"] - k["open"])
        upper_wick = k["high"] - max(k["close"], k["open"])
        lower_wick = min(k["close"], k["open"]) - k["low"]

        # 锤子线条件: 下影线 > 实体*2, 上影线 < 实体
        if body > 0 and lower_wick > body * 2 and upper_wick < body:
            entry_price = k["close"]
            entry_time = k["datetime"]

            max_gain = 0
            max_loss = 0

            for j in range(i+1, min(i+25, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            signals.append({
                "type": "看涨插针",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "index": i
            })

    return signals


def detect_breakout(klines: List[Dict], lookback: int = 7) -> List[Dict]:
    """
    检测突破买入信号 (突破前N日高点)
    """
    signals = []

    for i in range(lookback, len(klines)):
        # 计算前N日最高价
        prev_high = max(k["high"] for k in klines[i-lookback:i])

        # 今日收盘突破前N日高点
        if klines[i]["close"] > prev_high and klines[i-1]["close"] <= prev_high:
            entry_price = klines[i]["close"]
            entry_time = klines[i]["datetime"]

            max_gain = 0
            max_loss = 0

            for j in range(i+1, min(i+25, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            signals.append({
                "type": "突破买入",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "index": i
            })

    return signals


def detect_golden_cross(klines: List[Dict]) -> List[Dict]:
    """
    检测EMA50/200黄金交叉
    """
    closes = [k["close"] for k in klines]
    ema50 = calculate_ema(closes, 50)
    ema200 = calculate_ema(closes, 200)

    signals = []

    for i in range(201, len(klines)):
        if ema50[i-1] <= ema200[i-1] and ema50[i] > ema200[i]:
            entry_price = klines[i]["close"]
            entry_time = klines[i]["datetime"]

            max_gain = 0
            max_loss = 0

            # 黄金交叉是长期信号，看更长周期
            for j in range(i+1, min(i+100, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            signals.append({
                "type": "EMA50/200黄金交叉",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "index": i
            })

    return signals


def detect_panic_dip(klines: List[Dict], rsi_threshold: int = 30,
                     drop_threshold: float = 5.0) -> List[Dict]:
    """
    检测恐慌+闪崩信号 (RSI超卖 + 大跌)
    """
    closes = [k["close"] for k in klines]
    rsi = calculate_rsi(closes, 14)

    signals = []

    for i in range(15, len(klines)):
        # 计算24小时跌幅
        if i >= 24:
            drop_24h = (klines[i]["close"] - klines[i-24]["close"]) / klines[i-24]["close"] * 100
        else:
            drop_24h = 0

        # 恐慌条件: RSI < 30 且 24小时跌幅 > 5%
        if rsi[i] < rsi_threshold and drop_24h < -drop_threshold:
            entry_price = klines[i]["close"]
            entry_time = klines[i]["datetime"]

            max_gain = 0
            max_loss = 0

            for j in range(i+1, min(i+49, len(klines))):
                high_pct = (klines[j]["high"] - entry_price) / entry_price * 100
                low_pct = (klines[j]["low"] - entry_price) / entry_price * 100

                max_gain = max(max_gain, high_pct)
                max_loss = min(max_loss, low_pct)

            signals.append({
                "type": "恐慌+闪崩",
                "entry_time": entry_time,
                "entry_price": entry_price,
                "max_gain": max_gain,
                "max_loss": abs(max_loss),
                "rsi": rsi[i],
                "drop_24h": drop_24h,
                "index": i
            })

    return signals


# ============================================
# 回测引擎
# ============================================

def backtest_strategy_with_tp_sl(signals: List[Dict], klines: List[Dict],
                                  tp_pct: float, sl_pct: float,
                                  leverage: int = 10,
                                  initial_capital: float = 10000) -> Dict:
    """
    对策略信号进行止盈止损回测

    返回:
    - 总收益
    - 胜率
    - 最大回撤
    - 每笔交易详情
    """
    capital = initial_capital
    trades = []
    wins = 0
    losses = 0
    peak_capital = capital
    max_drawdown = 0

    for signal in signals:
        entry_idx = signal["index"]
        entry_price = signal["entry_price"]

        # 计算止盈止损价格
        tp_price = entry_price * (1 + tp_pct / 100)
        sl_price = entry_price * (1 - sl_pct / 100)

        # 模拟交易执行
        exit_price = None
        exit_reason = None
        exit_time = None

        # 检查后续K线，看是否触发止盈或止损
        for j in range(entry_idx + 1, min(entry_idx + 100, len(klines))):
            k = klines[j]

            # 先检查止损（假设止损先触发）
            if k["low"] <= sl_price:
                exit_price = sl_price
                exit_reason = "止损"
                exit_time = k["datetime"]
                break

            # 再检查止盈
            if k["high"] >= tp_price:
                exit_price = tp_price
                exit_reason = "止盈"
                exit_time = k["datetime"]
                break

        # 如果100根K线内都没触发，按收盘价平仓
        if exit_price is None:
            exit_idx = min(entry_idx + 100, len(klines) - 1)
            exit_price = klines[exit_idx]["close"]
            exit_reason = "超时平仓"
            exit_time = klines[exit_idx]["datetime"]

        # 计算收益
        pnl_pct = (exit_price - entry_price) / entry_price * leverage
        pnl_amount = capital * pnl_pct

        # 限制最大亏损为本金
        if pnl_pct < -1:
            pnl_pct = -1
            pnl_amount = -capital

        capital += pnl_amount

        # 统计胜负
        if pnl_pct > 0:
            wins += 1
        else:
            losses += 1

        # 更新最大回撤
        if capital > peak_capital:
            peak_capital = capital
        drawdown = (peak_capital - capital) / peak_capital if peak_capital > 0 else 0
        max_drawdown = max(max_drawdown, drawdown)

        trades.append({
            "entry_time": signal["entry_time"],
            "entry_price": entry_price,
            "exit_time": exit_time,
            "exit_price": exit_price,
            "exit_reason": exit_reason,
            "pnl_pct": pnl_pct * 100,
            "pnl_amount": pnl_amount,
            "capital_after": capital
        })

        # 爆仓检查
        if capital <= 0:
            break

    total_trades = len(trades)
    win_rate = wins / total_trades * 100 if total_trades > 0 else 0
    total_return = (capital - initial_capital) / initial_capital * 100

    return {
        "strategy_type": signals[0]["type"] if signals else "Unknown",
        "tp_pct": tp_pct,
        "sl_pct": sl_pct,
        "leverage": leverage,
        "initial_capital": initial_capital,
        "final_capital": capital,
        "total_return": total_return,
        "total_trades": total_trades,
        "wins": wins,
        "losses": losses,
        "win_rate": win_rate,
        "max_drawdown": max_drawdown * 100,
        "trades": trades
    }


# ============================================
# 主回测流程
# ============================================

def run_full_backtest():
    """运行完整回测"""
    print("=" * 70)
    print("BTC/USDT 真实历史数据回测系统")
    print("=" * 70)

    # 获取历史数据 (1小时K线，2年数据)
    klines = fetch_all_historical_data("BTCUSDT", "1h", 730)

    if not klines:
        print("❌ 无法获取历史数据，请检查网络连接")
        return None

    print(f"\n数据范围: {klines[0]['datetime']} 至 {klines[-1]['datetime']}")
    print(f"BTC价格范围: ${min(k['low'] for k in klines):,.0f} - ${max(k['high'] for k in klines):,.0f}")

    # 检测各策略信号
    print("\n" + "=" * 70)
    print("检测策略信号...")
    print("=" * 70)

    all_strategies = {}

    # 1. EMA7/25金叉
    signals = detect_ema_crossover(klines, 7, 25)
    all_strategies["EMA7/25金叉"] = signals
    print(f"EMA7/25金叉: 发现 {len(signals)} 个信号")

    # 2. 趋势EMA交叉
    signals = detect_trend_ema_crossover(klines)
    all_strategies["趋势EMA交叉"] = signals
    print(f"趋势EMA交叉: 发现 {len(signals)} 个信号")

    # 3. 看涨插针
    signals = detect_pin_bar(klines)
    all_strategies["看涨插针"] = signals
    print(f"看涨插针: 发现 {len(signals)} 个信号")

    # 4. 突破买入
    signals = detect_breakout(klines)
    all_strategies["突破买入"] = signals
    print(f"突破买入: 发现 {len(signals)} 个信号")

    # 5. EMA50/200黄金交叉
    signals = detect_golden_cross(klines)
    all_strategies["EMA50/200黄金交叉"] = signals
    print(f"EMA50/200黄金交叉: 发现 {len(signals)} 个信号")

    # 6. 恐慌+闪崩
    signals = detect_panic_dip(klines)
    all_strategies["恐慌+闪崩"] = signals
    print(f"恐慌+闪崩: 发现 {len(signals)} 个信号")

    # 最优参数（来自遍历优化）
    optimal_params = {
        "趋势EMA交叉": {"tp": 55, "sl": 1},
        "EMA7/25金叉": {"tp": 50, "sl": 1},
        "突破买入": {"tp": 55, "sl": 1},
        "恐慌+闪崩": {"tp": 125, "sl": 1},
        "看涨插针": {"tp": 55, "sl": 1},
        "EMA50/200黄金交叉": {"tp": 80, "sl": 1},
    }

    # 回测各策略
    print("\n" + "=" * 70)
    print("执行真实数据回测 (20x杠杆)")
    print("=" * 70)

    backtest_results = []

    for strategy_name, signals in all_strategies.items():
        if not signals:
            print(f"\n{strategy_name}: 无信号，跳过")
            continue

        params = optimal_params.get(strategy_name, {"tp": 50, "sl": 2})

        result = backtest_strategy_with_tp_sl(
            signals, klines,
            tp_pct=params["tp"],
            sl_pct=params["sl"],
            leverage=20,
            initial_capital=10000
        )

        backtest_results.append(result)

        print(f"\n📊 {strategy_name}")
        print(f"   参数: 止盈{params['tp']}% / 止损{params['sl']}%")
        print(f"   交易次数: {result['total_trades']}")
        print(f"   胜率: {result['win_rate']:.1f}%")
        print(f"   总收益: {result['total_return']:,.1f}%")
        print(f"   最大回撤: {result['max_drawdown']:.1f}%")
        print(f"   最终资金: ${result['final_capital']:,.2f}")

    # 生成HTML报告
    generate_backtest_report(backtest_results, klines)

    return backtest_results


def generate_backtest_report(results: List[Dict], klines: List[Dict]):
    """生成回测报告HTML"""

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>BTC策略真实回测报告</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
               background: linear-gradient(135deg, #0f0c29 0%, #302b63 50%, #24243e 100%);
               color: #e0e0e0; line-height: 1.6; padding: 20px; min-height: 100vh; }}
        .container {{ max-width: 1400px; margin: 0 auto; }}
        h1 {{ text-align: center; color: #00d4ff; font-size: 2.2em; margin-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #888; margin-bottom: 30px; }}
        h2 {{ color: #00d4ff; margin: 30px 0 20px; }}
        .warning {{ background: rgba(255, 100, 100, 0.2); border: 2px solid #ff6b6b;
                   border-radius: 10px; padding: 15px; margin: 20px 0; }}
        .info-box {{ background: rgba(0, 212, 255, 0.1); border: 1px solid #00d4ff;
                    border-radius: 10px; padding: 15px; margin: 20px 0; }}
        table {{ width: 100%; border-collapse: collapse; margin: 20px 0;
                background: rgba(0, 0, 0, 0.3); border-radius: 10px; overflow: hidden; }}
        th, td {{ padding: 12px 15px; text-align: center; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        th {{ background: rgba(0, 212, 255, 0.2); color: #00d4ff; font-weight: 600; }}
        tr:hover {{ background: rgba(255, 255, 255, 0.05); }}
        .green {{ color: #00ff88; }}
        .red {{ color: #ff6b6b; }}
        .gold {{ color: #ffd700; }}
        .strategy-card {{ background: rgba(0, 0, 0, 0.3); border-radius: 15px; padding: 20px;
                         margin: 20px 0; border-left: 4px solid #00d4ff; }}
        .strategy-header {{ display: flex; justify-content: space-between; align-items: center;
                           flex-wrap: wrap; gap: 15px; margin-bottom: 15px; }}
        .strategy-name {{ font-size: 1.4em; color: #00d4ff; }}
        .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr));
                      gap: 15px; margin: 15px 0; }}
        .stat-item {{ background: rgba(0, 212, 255, 0.1); padding: 15px; border-radius: 10px; text-align: center; }}
        .stat-value {{ font-size: 1.5em; font-weight: bold; color: #00ff88; }}
        .stat-label {{ color: #888; font-size: 0.9em; }}
        .trade-list {{ max-height: 300px; overflow-y: auto; }}
        .footer {{ text-align: center; margin-top: 40px; color: #666; padding: 20px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>📈 BTC/USDT 策略真实回测报告</h1>
        <p class="subtitle">使用币安历史K线数据 | {klines[0]['datetime']} 至 {klines[-1]['datetime']} | 共{len(klines)}根K线</p>

        <div class="warning">
            <strong>⚠️ 重要风险提示:</strong><br>
            • 历史表现不代表未来收益<br>
            • 回测未考虑交易手续费、滑点、资金费率<br>
            • 1%止损在高杠杆下可能因价格跳空而被击穿<br>
            • 实盘交易请务必控制仓位，设置好止损
        </div>

        <div class="info-box">
            <strong>📊 回测参数:</strong><br>
            • 杠杆: 20x | 初始资金: $10,000<br>
            • 数据周期: 1小时K线 | 数据量: {len(klines)}条<br>
            • BTC价格范围: ${min(k['low'] for k in klines):,.0f} - ${max(k['high'] for k in klines):,.0f}
        </div>

        <h2>📊 各策略回测结果</h2>
        <table>
            <thead>
                <tr>
                    <th>策略</th>
                    <th>止盈/止损</th>
                    <th>交易次数</th>
                    <th>胜率</th>
                    <th>总收益</th>
                    <th>最大回撤</th>
                    <th>最终资金</th>
                </tr>
            </thead>
            <tbody>'''

    for r in sorted(results, key=lambda x: x['total_return'], reverse=True):
        profit_class = "green" if r['total_return'] > 0 else "red"
        html += f'''
                <tr>
                    <td><strong>{r['strategy_type']}</strong></td>
                    <td>{r['tp_pct']}% / {r['sl_pct']}%</td>
                    <td>{r['total_trades']}</td>
                    <td class="{'green' if r['win_rate'] >= 50 else 'red'}">{r['win_rate']:.1f}%</td>
                    <td class="{profit_class}"><strong>{r['total_return']:,.1f}%</strong></td>
                    <td class="red">{r['max_drawdown']:.1f}%</td>
                    <td class="{profit_class}">${r['final_capital']:,.2f}</td>
                </tr>'''

    html += '''
            </tbody>
        </table>'''

    # 每个策略的详细交易记录
    for r in results:
        if r['total_trades'] == 0:
            continue

        html += f'''
        <div class="strategy-card">
            <div class="strategy-header">
                <div class="strategy-name">📈 {r['strategy_type']}</div>
            </div>

            <div class="stats-grid">
                <div class="stat-item">
                    <div class="stat-value">{r['total_trades']}</div>
                    <div class="stat-label">交易次数</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: {'#00ff88' if r['win_rate'] >= 50 else '#ff6b6b'}">{r['win_rate']:.1f}%</div>
                    <div class="stat-label">胜率</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: {'#00ff88' if r['total_return'] > 0 else '#ff6b6b'}">{r['total_return']:,.1f}%</div>
                    <div class="stat-label">总收益</div>
                </div>
                <div class="stat-item">
                    <div class="stat-value" style="color: #ff6b6b">{r['max_drawdown']:.1f}%</div>
                    <div class="stat-label">最大回撤</div>
                </div>
            </div>

            <h4 style="color: #ffd700; margin: 15px 0;">交易记录 (前20笔)</h4>
            <div class="trade-list">
                <table>
                    <thead>
                        <tr>
                            <th>入场时间</th>
                            <th>入场价</th>
                            <th>出场时间</th>
                            <th>出场价</th>
                            <th>出场原因</th>
                            <th>盈亏%</th>
                            <th>账户余额</th>
                        </tr>
                    </thead>
                    <tbody>'''

        for trade in r['trades'][:20]:
            pnl_class = "green" if trade['pnl_pct'] > 0 else "red"
            reason_class = "green" if trade['exit_reason'] == "止盈" else ("red" if trade['exit_reason'] == "止损" else "gold")
            html += f'''
                        <tr>
                            <td>{trade['entry_time']}</td>
                            <td>${trade['entry_price']:,.2f}</td>
                            <td>{trade['exit_time']}</td>
                            <td>${trade['exit_price']:,.2f}</td>
                            <td class="{reason_class}">{trade['exit_reason']}</td>
                            <td class="{pnl_class}">{trade['pnl_pct']:+.1f}%</td>
                            <td>${trade['capital_after']:,.2f}</td>
                        </tr>'''

        html += '''
                    </tbody>
                </table>
            </div>
        </div>'''

    html += f'''
        <div class="footer">
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</p>
            <p>⚠️ 本报告仅供学习参考，不构成投资建议</p>
        </div>
    </div>
</body>
</html>'''

    report_path = "/home/user/zk-2048/trading_strategy/reports/真实数据回测报告.html"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n✅ 回测报告已保存: {report_path}")


if __name__ == "__main__":
    run_full_backtest()
