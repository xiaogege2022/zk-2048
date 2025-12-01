#!/usr/bin/env python3
"""
验证回测真实性 - 显示每笔交易的详细信息
确认止盈止损是否真实触发
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from comprehensive_backtest import load_data, add_all_indicators, get_combo_signals

def detailed_backtest(df, signal_array, tp_pct, sl_pct, hold_bars=100, name=""):
    """详细回测 - 显示每笔交易的完整信息"""
    trades = []

    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    open_arr = df['open'].values
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

            exit_price, exit_time, exit_reason = None, None, None
            bars_held = 0

            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                bars_held = j - i

                # 先检查止损（同一根K线可能同时触及止盈止损，优先止损更保守）
                if low_arr[j] <= sl_price:
                    exit_price = sl_price
                    exit_time = timestamps[j]
                    exit_reason = 'STOP_LOSS'
                    break

                # 再检查止盈
                if high_arr[j] >= tp_price:
                    exit_price = tp_price
                    exit_time = timestamps[j]
                    exit_reason = 'TAKE_PROFIT'
                    break

            if exit_price is None:
                j = min(i + hold_bars, n - 1)
                exit_price = close_arr[j]
                exit_time = timestamps[j]
                exit_reason = 'TIMEOUT'
                bars_held = j - i

            pnl_pct = (exit_price - entry_price) / entry_price * 100
            pnl_with_lev = pnl_pct * 10  # 假设10倍杠杆

            trades.append({
                'strategy': name,
                'entry_time': entry_time,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'bars_held': bars_held,
                'pnl_pct': pnl_pct,
                'pnl_10x': pnl_with_lev,
                'win': pnl_pct > 0,
            })
            i = j + 1
        else:
            i += 1

    return trades


def verify_strategy(strategy_name, timeframe, tp_pct=100, sl_pct=5):
    """验证单个策略的回测结果"""
    print(f"\n{'='*80}")
    print(f"验证策略: {strategy_name} | 周期: {timeframe}")
    print(f"参数: TP={tp_pct}% SL={sl_pct}%")
    print(f"{'='*80}")

    # 加载数据
    data = load_data()

    if timeframe not in data:
        print(f"错误: {timeframe} 数据不存在")
        return

    df = add_all_indicators(data[timeframe], data['fear_greed'], data['funding'])
    signals = get_combo_signals(df)

    if strategy_name not in signals:
        print(f"错误: 策略 {strategy_name} 不存在")
        return

    signal_arr = signals[strategy_name]
    signal_count = np.sum(signal_arr)
    print(f"\n信号总数: {signal_count}")

    # 详细回测
    trades = detailed_backtest(df, signal_arr, tp_pct, sl_pct, hold_bars=100, name=strategy_name)

    if not trades:
        print("没有产生交易")
        return

    print(f"实际交易数: {len(trades)}")
    print(f"\n{'='*80}")
    print("详细交易记录:")
    print(f"{'='*80}")
    print(f"{'#':<3} {'入场时间':<20} {'入场价':<12} {'止盈价':<12} {'止损价':<12} {'出场价':<12} {'出场原因':<12} {'盈亏%':<10} {'结果':<6}")
    print("-" * 110)

    wins = 0
    losses = 0
    timeouts = 0

    for i, t in enumerate(trades, 1):
        entry_time = pd.Timestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M')
        result = '✓ 盈' if t['win'] else '✗ 亏'
        reason_cn = {
            'TAKE_PROFIT': '止盈触发',
            'STOP_LOSS': '止损触发',
            'TIMEOUT': '超时平仓'
        }.get(t['exit_reason'], t['exit_reason'])

        if t['exit_reason'] == 'TAKE_PROFIT':
            wins += 1
        elif t['exit_reason'] == 'STOP_LOSS':
            losses += 1
        else:
            timeouts += 1
            if t['win']:
                wins += 1
            else:
                losses += 1

        print(f"{i:<3} {entry_time:<20} ${t['entry_price']:<11,.0f} ${t['tp_price']:<11,.0f} ${t['sl_price']:<11,.0f} ${t['exit_price']:<11,.0f} {reason_cn:<12} {t['pnl_pct']:>+8.2f}% {result}")

    # 统计
    total = len(trades)
    win_rate = wins / total * 100 if total > 0 else 0

    print(f"\n{'='*80}")
    print("统计汇总:")
    print(f"{'='*80}")
    print(f"总交易数: {total}")
    print(f"止盈触发: {wins} ({wins/total*100:.1f}%)" if total > 0 else "止盈触发: 0")
    print(f"止损触发: {losses} ({losses/total*100:.1f}%)" if total > 0 else "止损触发: 0")
    print(f"超时平仓: {timeouts} ({timeouts/total*100:.1f}%)" if total > 0 else "超时平仓: 0")
    print(f"实际胜率: {win_rate:.1f}%")

    # 计算EV
    ev = (win_rate/100 * tp_pct * 10) - ((1 - win_rate/100) * sl_pct * 10)
    print(f"EV (10x杠杆): {ev:.1f}%")


def main():
    print("\n" + "=" * 80)
    print("回测验证系统 - 确认止盈止损真实触发")
    print("=" * 80)

    # 验证用户关心的策略
    strategies_to_verify = [
        ('恐惧+Pin Bar', '1w', 100, 5),
        ('RSI超卖+恐惧', '1w', 100, 5),
        ('极度恐惧+闪崩', '1h', 100, 5),
        ('极度恐惧+闪崩', '1d', 100, 5),
        ('MACD金叉+RSI回升+趋势', '1d', 100, 5),
        ('EMA金叉+放量', '4h', 100, 5),
        ('完美抄底', '4h', 100, 5),
    ]

    for strategy, tf, tp, sl in strategies_to_verify:
        verify_strategy(strategy, tf, tp, sl)
        print("\n")


if __name__ == "__main__":
    main()
