#!/usr/bin/env python3
"""
BTC/USDT 最终验证回测报告
- 所有策略经过真实K线回测
- 包含固定止盈止损和移动止盈止损
- 显示每笔交易详情
- 覆盖所有时间周期: 1w, 1d, 4h, 1h
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from comprehensive_backtest import load_data, add_all_indicators, get_combo_signals, STRATEGY_DESCRIPTIONS


def backtest_fixed(df, signal_array, tp_pct, sl_pct, leverage, hold_bars=100):
    """固定止盈止损回测

    参数说明:
    - tp_pct: 账户止盈百分比 (杠杆后), 例如 100 表示账户盈利100%时止盈
    - sl_pct: 账户止损百分比 (杠杆后), 例如 20 表示账户亏损20%时止损
    - leverage: 杠杆倍数

    现货价格计算:
    - 现货止盈涨幅 = 账户止盈% / 杠杆
    - 现货止损跌幅 = 账户止损% / 杠杆
    """
    trades = []
    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    warmup = min(250, n // 4)
    i = warmup

    # 根据杠杆反算现货价格变化
    spot_tp_pct = tp_pct / leverage  # 现货止盈百分比
    spot_sl_pct = sl_pct / leverage  # 现货止损百分比

    while i < n - hold_bars:
        if signal_array[i]:
            entry_price = close_arr[i]
            entry_time = timestamps[i]
            tp_price = entry_price * (1 + spot_tp_pct / 100)
            sl_price = entry_price * (1 - spot_sl_pct / 100)
            highest_price = entry_price  # 追踪最高价

            exit_price, exit_time, exit_reason = None, None, None

            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                # 更新最高价
                if high_arr[j] > highest_price:
                    highest_price = high_arr[j]
                # 先检查止损
                if low_arr[j] <= sl_price:
                    exit_price, exit_time, exit_reason = sl_price, timestamps[j], 'SL'
                    break
                # 再检查止盈
                if high_arr[j] >= tp_price:
                    exit_price, exit_time, exit_reason = tp_price, timestamps[j], 'TP'
                    break

            if exit_price is None:
                j = min(i + hold_bars, n - 1)
                exit_price = close_arr[j]
                exit_time = timestamps[j]
                exit_reason = 'TIMEOUT'

            spot_pnl_pct = (exit_price - entry_price) / entry_price * 100  # 现货盈亏%
            account_pnl_pct = spot_pnl_pct * leverage  # 账户盈亏% = 现货盈亏% × 杠杆
            trades.append({
                'entry_time': entry_time,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'highest_price': highest_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'spot_pnl_pct': spot_pnl_pct,  # 现货盈亏%
                'pnl_pct': account_pnl_pct,    # 账户盈亏% (杠杆后)
                'tp_type': 'fixed',
            })
            i = j + 1
        else:
            i += 1

    return trades


def backtest_trailing(df, signal_array, tp_pct, sl_pct, trail_pct, leverage, hold_bars=100):
    """移动止盈止损回测 - 避免资金回撤

    参数说明:
    - tp_pct: 账户止盈百分比 (杠杆后)
    - sl_pct: 账户止损百分比 (杠杆后)
    - trail_pct: 账户移动止损百分比 (杠杆后), 从最高盈利回撤此比例时触发
    - leverage: 杠杆倍数
    """
    trades = []
    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    warmup = min(250, n // 4)
    i = warmup

    # 根据杠杆反算现货价格变化
    spot_tp_pct = tp_pct / leverage
    spot_sl_pct = sl_pct / leverage
    spot_trail_pct = trail_pct / leverage

    while i < n - hold_bars:
        if signal_array[i]:
            entry_price = close_arr[i]
            entry_time = timestamps[i]
            tp_price = entry_price * (1 + spot_tp_pct / 100)
            initial_sl_price = entry_price * (1 - spot_sl_pct / 100)
            current_sl_price = initial_sl_price
            highest_price = entry_price

            exit_price, exit_time, exit_reason = None, None, None

            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                # 更新最高价
                if high_arr[j] > highest_price:
                    highest_price = high_arr[j]
                    # 移动止损: 最高价回撤 spot_trail_pct% (现货百分比)
                    new_trail_sl = highest_price * (1 - spot_trail_pct / 100)
                    if new_trail_sl > current_sl_price:
                        current_sl_price = new_trail_sl

                # 检查止损 (包括移动止损)
                if low_arr[j] <= current_sl_price:
                    exit_price = current_sl_price
                    exit_time = timestamps[j]
                    # 判断是初始止损还是移动止损触发
                    if current_sl_price > initial_sl_price:
                        exit_reason = 'TRAIL_SL'  # 移动止损 (保本或盈利出场)
                    else:
                        exit_reason = 'SL'  # 初始止损
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

            spot_pnl_pct = (exit_price - entry_price) / entry_price * 100  # 现货盈亏%
            account_pnl_pct = spot_pnl_pct * leverage  # 账户盈亏% = 现货盈亏% × 杠杆
            trades.append({
                'entry_time': entry_time,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'initial_sl': initial_sl_price,
                'final_sl': current_sl_price,
                'highest_price': highest_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'spot_pnl_pct': spot_pnl_pct,  # 现货盈亏%
                'pnl_pct': account_pnl_pct,    # 账户盈亏% (杠杆后)
                'tp_type': 'trailing',
                'trail_pct': trail_pct,  # 账户移动止损%
            })
            i = j + 1
        else:
            i += 1

    return trades


def calculate_stats(trades):
    """计算交易统计"""
    if not trades:
        return None

    total = len(trades)
    tp_wins = sum(1 for t in trades if t['exit_reason'] == 'TP')
    sl_losses = sum(1 for t in trades if t['exit_reason'] == 'SL')
    trail_exits = sum(1 for t in trades if t['exit_reason'] == 'TRAIL_SL')
    timeouts = sum(1 for t in trades if t['exit_reason'] == 'TIMEOUT')

    wins = sum(1 for t in trades if t['pnl_pct'] > 0)
    win_rate = wins / total * 100

    # 理论胜率: 持仓期间最高价 > 入场价的交易比例 (不含止盈止损的胜率)
    theory_wins = sum(1 for t in trades if t.get('highest_price', t['entry_price']) > t['entry_price'])
    theory_win_rate = theory_wins / total * 100

    total_pnl = sum(t['pnl_pct'] for t in trades)
    avg_pnl = total_pnl / total

    return {
        'total': total,
        'tp_wins': tp_wins,
        'sl_losses': sl_losses,
        'trail_exits': trail_exits,
        'timeouts': timeouts,
        'wins': wins,
        'win_rate': win_rate,
        'theory_win_rate': theory_win_rate,
        'total_pnl': total_pnl,
        'avg_pnl': avg_pnl,
    }


def run_full_backtest():
    """运行完整回测"""
    print("=" * 80)
    print("BTC/USDT 最终验证回测报告")
    print("包含: 固定止盈止损 + 移动止盈止损 | 所有周期")
    print("=" * 80)

    data = load_data()
    timeframes = ['1w', '1d', '4h', '1h']

    # 参数范围 - 全部为账户百分比 (杠杆后)
    # 止盈: 账户盈利多少%时止盈
    tp_range = [50, 75, 100, 150, 200, 300]
    # 止损: 账户亏损多少%时止损 (合理范围: 10-40%)
    sl_range = [10, 15, 20, 25, 30, 40]
    # 移动止损: 从最高盈利回撤多少%时触发 (账户百分比)
    trail_range = [10, 15, 20, 25, 30]
    # 杠杆倍数
    lev_range = [5, 10, 15, 20, 25]

    all_results = []

    for tf in timeframes:
        if tf not in data:
            continue

        print(f"\n{'='*60}")
        print(f"时间周期: {tf}")
        print(f"{'='*60}")

        df = add_all_indicators(data[tf], data['fear_greed'], data['funding'])
        signals = get_combo_signals(df)

        for strategy_name, signal_arr in signals.items():
            signal_count = np.sum(signal_arr)
            if signal_count < 2:
                continue

            print(f"  {strategy_name}... ", end="", flush=True)

            best_fixed = None
            best_fixed_ev = -float('inf')
            best_trail = None
            best_trail_ev = -float('inf')

            # 测试固定止盈止损 - 参数现在是账户百分比
            for lev in lev_range:
                for tp in tp_range:
                    for sl in sl_range:
                        # 盈亏比至少 2:1
                        if tp / sl < 2:
                            continue

                        # 回测时传入杠杆，函数内部会反算现货价格
                        trades = backtest_fixed(df, signal_arr, tp, sl, lev, hold_bars=100)
                        if len(trades) < 2:
                            continue

                        stats = calculate_stats(trades)
                        if stats is None:
                            continue

                        # EV计算 - tp和sl已经是账户百分比，不需要再乘杠杆
                        ev = (stats['win_rate']/100 * tp) - ((1 - stats['win_rate']/100) * sl)

                        if ev > best_fixed_ev:
                            best_fixed_ev = ev
                            best_fixed = {
                                'strategy': strategy_name,
                                'timeframe': tf,
                                'tp_type': 'fixed',
                                'tp': tp,      # 账户止盈%
                                'sl': sl,      # 账户止损%
                                'trail': 0,
                                'leverage': lev,
                                **stats,
                                'ev': ev,
                                'trades_detail': trades,
                            }

            # 测试移动止盈止损 - 参数现在是账户百分比
            for lev in lev_range:
                for tp in tp_range:
                    for sl in sl_range:
                        for trail in trail_range:
                            # 盈亏比至少 2:1
                            if tp / sl < 2:
                                continue

                            # 回测时传入杠杆，函数内部会反算现货价格
                            trades = backtest_trailing(df, signal_arr, tp, sl, trail, lev, hold_bars=100)
                            if len(trades) < 2:
                                continue

                            stats = calculate_stats(trades)
                            if stats is None:
                                continue

                            # EV计算 - tp和sl已经是账户百分比
                            ev = (stats['win_rate']/100 * tp) - ((1 - stats['win_rate']/100) * sl)

                            if ev > best_trail_ev:
                                best_trail_ev = ev
                                best_trail = {
                                    'strategy': strategy_name,
                                    'timeframe': tf,
                                    'tp_type': 'trailing',
                                    'tp': tp,      # 账户止盈%
                                    'sl': sl,      # 账户止损%
                                    'trail': trail,  # 账户移动止损%
                                    'leverage': lev,
                                    **stats,
                                    'ev': ev,
                                    'trades_detail': trades,
                                }

            # 添加最佳结果
            results_added = []
            if best_fixed:
                all_results.append(best_fixed)
                results_added.append(f"固定:{best_fixed['win_rate']:.1f}%/{best_fixed['ev']:.0f}%")

            if best_trail:
                all_results.append(best_trail)
                results_added.append(f"移动:{best_trail['win_rate']:.1f}%/{best_trail['ev']:.0f}%")

            if results_added:
                print(" | ".join(results_added))
            else:
                print("无有效结果")

    return all_results


def generate_html_report(results):
    """生成HTML报告"""

    # 分离固定和移动止盈止损结果
    fixed_results = [r for r in results if r['tp_type'] == 'fixed']
    trail_results = [r for r in results if r['tp_type'] == 'trailing']

    # 按EV排序
    fixed_sorted = sorted(fixed_results, key=lambda x: x['ev'], reverse=True)
    trail_sorted = sorted(trail_results, key=lambda x: x['ev'], reverse=True)
    all_sorted = sorted(results, key=lambda x: x['ev'], reverse=True)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 最终验证回测报告</title>
    <style>
        body {{
            font-family: 'Segoe UI', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #0d1117, #161b22, #21262d);
            color: #e6edf3;
            margin: 0;
            padding: 20px;
            min-height: 100vh;
        }}
        .container {{ max-width: 1800px; margin: 0 auto; }}
        h1 {{
            text-align: center;
            color: #ffd700;
            font-size: 2.5em;
            text-shadow: 0 0 20px rgba(255, 215, 0, 0.5);
        }}
        .warning {{
            background: rgba(46, 160, 67, 0.15);
            border: 2px solid #2ea043;
            border-radius: 10px;
            padding: 15px;
            margin: 20px 0;
            text-align: center;
        }}
        .section {{
            background: rgba(255,255,255,0.02);
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
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.8em; }}
        th {{
            background: rgba(255, 215, 0, 0.15);
            color: #ffd700;
            padding: 10px 5px;
            text-align: left;
            position: sticky;
            top: 0;
        }}
        td {{ padding: 8px 5px; border-bottom: 1px solid rgba(255,255,255,0.05); }}
        tr:hover {{ background: rgba(255,215,0,0.03); }}
        .badge {{
            display: inline-block;
            padding: 2px 6px;
            border-radius: 6px;
            font-size: 0.7em;
            font-weight: bold;
        }}
        .badge-1w {{ background: #da3633; }}
        .badge-1d {{ background: #d29922; }}
        .badge-4h {{ background: #1f6feb; }}
        .badge-1h {{ background: #8957e5; }}
        .badge-fixed {{ background: #238636; }}
        .badge-trail {{ background: #1f6feb; }}
        .ev-high {{ color: #3fb950; font-weight: bold; }}
        .ev-medium {{ color: #d29922; }}
        .ev-low {{ color: #f85149; }}
        .win {{ color: #3fb950; }}
        .loss {{ color: #f85149; }}
        .highlight {{ background: rgba(255,215,0,0.08); }}
        .trade-box {{
            background: rgba(0,0,0,0.3);
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            max-height: 400px;
            overflow-y: auto;
        }}
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 15px;
            margin: 20px 0;
        }}
        .stat-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 10px;
            padding: 20px;
            text-align: center;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .stat-value {{ font-size: 2em; color: #ffd700; font-weight: bold; }}
        .stat-label {{ color: #8b949e; margin-top: 5px; font-size: 0.9em; }}
        .compare-table {{ margin: 20px 0; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 最终验证回测报告</h1>

        <div class="warning">
            <strong>✓ 所有数据已验证:</strong> 每笔交易都经过真实K线回测，严格执行止盈止损，
            止损优先于止盈触发，移动止损用于锁定利润避免回撤。
        </div>

        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(results)}</div>
                <div class="stat-label">总策略配置数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(fixed_results)}</div>
                <div class="stat-label">固定止盈止损</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{len(trail_results)}</div>
                <div class="stat-label">移动止盈止损</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{max(r['ev'] for r in results):.0f}%</div>
                <div class="stat-label">最高EV</div>
            </div>
        </div>

        <!-- Top 30 综合排名 -->
        <div class="section">
            <h2>Top 30 最优EV策略 (综合排名)</h2>
            <p style="color:#8b949e; font-size:0.9em;">注: TP%/SL%/移动% 均为<b style="color:#ffd700;">账户盈亏百分比</b>(杠杆后)，例如 TP=100% 表示账户盈利100%时止盈</p>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>周期</th>
                    <th>类型</th>
                    <th>账户止盈%</th>
                    <th>账户止损%</th>
                    <th>移动止损%</th>
                    <th>杠杆</th>
                    <th>交易</th>
                    <th>止盈</th>
                    <th>止损</th>
                    <th>移动出</th>
                    <th>超时</th>
                    <th>理论胜率</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""

    for i, r in enumerate(all_sorted[:30], 1):
        tf_class = f"badge-{r['timeframe']}"
        tp_class = "badge-trail" if r['tp_type'] == 'trailing' else "badge-fixed"
        tp_name = "移动" if r['tp_type'] == 'trailing' else "固定"
        # EV现在是账户百分比，不再乘杠杆，所以阈值调低
        ev_class = 'ev-high' if r['ev'] > 50 else 'ev-medium' if r['ev'] > 20 else 'ev-low'
        highlight = 'highlight' if i <= 5 else ''
        # 理论胜率: 持仓期间价格曾经上涨过的比例 (不含止盈止损)
        theory_wr = r.get('theory_win_rate', r['win_rate'])

        html += f"""
                <tr class="{highlight}">
                    <td>{i}</td>
                    <td>{r['strategy']}</td>
                    <td><span class="badge {tf_class}">{r['timeframe']}</span></td>
                    <td><span class="badge {tp_class}">{tp_name}</span></td>
                    <td>{r['tp']}%</td>
                    <td>{r['sl']}%</td>
                    <td>{r['trail']}%</td>
                    <td>{r['leverage']}x</td>
                    <td>{r['total']}</td>
                    <td class="win">{r['tp_wins']}</td>
                    <td class="loss">{r['sl_losses']}</td>
                    <td>{r.get('trail_exits', 0)}</td>
                    <td>{r['timeouts']}</td>
                    <td>{theory_wr:.1f}%</td>
                    <td>{r['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{r['ev']:.0f}%</td>
                </tr>"""

    html += """
            </table>
        </div>

        <!-- 移动止盈止损专区 -->
        <div class="section">
            <h2>移动止盈止损策略 Top 20 (锁定利润,避免回撤)</h2>
            <p style="color:#8b949e; font-size:0.9em;">注: 所有百分比均为<b style="color:#ffd700;">账户盈亏百分比</b>(杠杆后)</p>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>周期</th>
                    <th>账户止盈%</th>
                    <th>账户止损%</th>
                    <th>账户移动止损%</th>
                    <th>杠杆</th>
                    <th>交易</th>
                    <th>止盈</th>
                    <th>初始止损</th>
                    <th>移动止损出场</th>
                    <th>超时</th>
                    <th>理论胜率</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""

    for i, r in enumerate(trail_sorted[:20], 1):
        tf_class = f"badge-{r['timeframe']}"
        ev_class = 'ev-high' if r['ev'] > 50 else 'ev-medium' if r['ev'] > 20 else 'ev-low'
        theory_wr = r.get('theory_win_rate', r['win_rate'])  # 理论胜率

        html += f"""
                <tr>
                    <td>{i}</td>
                    <td>{r['strategy']}</td>
                    <td><span class="badge {tf_class}">{r['timeframe']}</span></td>
                    <td>{r['tp']}%</td>
                    <td>{r['sl']}%</td>
                    <td>{r['trail']}%</td>
                    <td>{r['leverage']}x</td>
                    <td>{r['total']}</td>
                    <td class="win">{r['tp_wins']}</td>
                    <td class="loss">{r['sl_losses']}</td>
                    <td>{r.get('trail_exits', 0)}</td>
                    <td>{r['timeouts']}</td>
                    <td>{theory_wr:.1f}%</td>
                    <td>{r['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{r['ev']:.0f}%</td>
                </tr>"""

    html += """
            </table>
        </div>
"""

    # 每个周期的详细交易记录
    for tf in ['1w', '1d', '4h', '1h']:
        tf_results = [r for r in all_sorted if r['timeframe'] == tf][:5]
        if not tf_results:
            continue

        tf_name = {'1w': '周线', '1d': '日线', '4h': '4小时', '1h': '1小时'}[tf]

        html += f"""
        <div class="section">
            <h2>{tf_name} ({tf}) Top 5 策略详细交易记录</h2>
"""

        for rank, r in enumerate(tf_results, 1):
            tp_name = "移动止盈止损" if r['tp_type'] == 'trailing' else "固定止盈止损"
            trail_info = f" 移动止损={r['trail']}%" if r['tp_type'] == 'trailing' else ""
            # 计算现货百分比供参考
            spot_tp = r['tp'] / r['leverage']
            spot_sl = r['sl'] / r['leverage']

            html += f"""
            <h3>{rank}. {r['strategy']} ({tp_name})</h3>
            <p><b>账户参数:</b> 止盈={r['tp']}% 止损={r['sl']}%{trail_info} 杠杆={r['leverage']}x |
               <b>现货价格:</b> 止盈涨幅={spot_tp:.2f}% 止损跌幅={spot_sl:.2f}% |
               <b>统计:</b> 交易={r['total']} 止盈={r['tp_wins']} 止损={r['sl_losses']}
               移动出场={r.get('trail_exits', 0)} 超时={r['timeouts']} |
               <b>胜率={r['win_rate']:.1f}%</b> <b>EV={r['ev']:.0f}%</b></p>
            <div class="trade-box">
                <table>
                    <tr>
                        <th>#</th>
                        <th>入场时间</th>
                        <th>入场价</th>
                        <th>止盈价</th>
                        <th>止损价</th>
                        <th>出场价</th>
                        <th>出场原因</th>
                        <th>现货涨跌%</th>
                        <th>账户盈亏%</th>
                    </tr>
"""

            trades = r['trades_detail']
            leverage = r['leverage']  # 获取杠杆倍数
            for j, t in enumerate(trades[:30], 1):  # 最多显示30笔
                entry_time = pd.Timestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M')
                reason_map = {
                    'TP': '止盈触发',
                    'SL': '止损触发',
                    'TRAIL_SL': '移动止损',
                    'TIMEOUT': '超时平仓'
                }
                reason_cn = reason_map.get(t['exit_reason'], t['exit_reason'])
                # pnl_pct 现在已经是账户盈亏%
                account_pnl = t['pnl_pct']
                spot_pnl = t.get('spot_pnl_pct', account_pnl / leverage)  # 兼容旧数据
                pnl_class = 'win' if account_pnl > 0 else 'loss'

                # 对于移动止损，显示最终止损价
                if r['tp_type'] == 'trailing':
                    sl_display = f"${t.get('final_sl', t.get('sl_price', 0)):,.0f}"
                else:
                    sl_display = f"${t['sl_price']:,.0f}"

                html += f"""
                    <tr>
                        <td>{j}</td>
                        <td>{entry_time}</td>
                        <td>${t['entry_price']:,.0f}</td>
                        <td>${t['tp_price']:,.0f}</td>
                        <td>{sl_display}</td>
                        <td>${t['exit_price']:,.0f}</td>
                        <td>{reason_cn}</td>
                        <td>{spot_pnl:+.2f}%</td>
                        <td class="{pnl_class}">{account_pnl:+.2f}%</td>
                    </tr>"""

            if len(trades) > 30:
                html += f"""
                    <tr><td colspan="9" style="text-align:center; color:#8b949e;">
                        ... 还有 {len(trades)-30} 笔交易 ...
                    </td></tr>"""

            html += """
                </table>
            </div>
"""

        html += """
        </div>
"""

    # 策略说明
    html += """
        <div class="section">
            <h2>策略条件说明</h2>
            <table>
                <tr>
                    <th>策略名称</th>
                    <th>触发条件</th>
                </tr>
"""

    for name, desc in STRATEGY_DESCRIPTIONS.items():
        html += f"""
                <tr>
                    <td><b>{name}</b></td>
                    <td>{desc}</td>
                </tr>"""

    html += f"""
            </table>
        </div>

        <div class="section">
            <h2>回测说明</h2>
            <ul>
                <li><b>参数单位:</b> 报告中的止盈%、止损%、移动止损% 均为<span style="color:#ffd700;">账户盈亏百分比</span>（杠杆后），而非现货涨跌幅</li>
                <li><b>价格计算:</b> 现货止盈涨幅 = 账户止盈% ÷ 杠杆，现货止损跌幅 = 账户止损% ÷ 杠杆</li>
                <li><b>举例:</b> 账户止盈100%、止损20%、杠杆20x → 现货止盈涨幅5%、现货止损跌幅1%</li>
                <li><b>固定止盈止损:</b> 入场后设置固定的止盈价和止损价，先触发哪个就按哪个价格出场</li>
                <li><b>移动止盈止损:</b> 价格创新高后，止损价跟随上移，锁定利润避免回撤</li>
                <li><b>止损优先:</b> 同一根K线可能同时触及止盈止损，本回测优先触发止损（更保守）</li>
                <li><b>超时平仓:</b> 持仓100根K线后未触及止盈止损，按收盘价平仓</li>
                <li><b>EV公式:</b> EV = (胜率 × 账户止盈%) - ((1-胜率) × 账户止损%)</li>
            </ul>
        </div>

        <div style="text-align: center; color: #8b949e; margin-top: 30px; padding: 20px;">
            <p>数据来源: Binance BTCUSDT 期货 | 2019-09 至 2025-11</p>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>
    </div>
</body>
</html>
"""

    with open('../reports/最终验证回测报告.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告已保存: ../reports/最终验证回测报告.html")


def main():
    results = run_full_backtest()

    if results:
        # 保存CSV (不含详细交易记录)
        csv_data = [{k: v for k, v in r.items() if k != 'trades_detail'} for r in results]
        df = pd.DataFrame(csv_data)
        df.to_csv('../reports/最终验证回测结果.csv', index=False)
        print(f"\nCSV已保存: ../reports/最终验证回测结果.csv")

        # 生成HTML报告
        generate_html_report(results)

    return results


if __name__ == "__main__":
    results = main()
