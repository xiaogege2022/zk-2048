#!/usr/bin/env python3
"""
真实回测报告生成器
- 确保每笔交易都经过止盈止损验证
- 显示详细的交易记录
- 修复之前的胜率计算bug
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from comprehensive_backtest import load_data, add_all_indicators, get_combo_signals, STRATEGY_DESCRIPTIONS


def real_backtest(df, signal_array, tp_pct, sl_pct, hold_bars=100):
    """真实回测 - 严格执行止盈止损"""
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

            exit_price, exit_time, exit_reason = None, None, None

            end_idx = min(i + hold_bars + 1, n)
            for j in range(i + 1, end_idx):
                # 先检查止损
                if low_arr[j] <= sl_price:
                    exit_price = sl_price
                    exit_time = timestamps[j]
                    exit_reason = 'SL'
                    break
                # 再检查止盈
                if high_arr[j] >= tp_price:
                    exit_price = tp_price
                    exit_time = timestamps[j]
                    exit_reason = 'TP'
                    break

            if exit_price is None:
                j = min(i + hold_bars, n - 1)
                exit_price = close_arr[j]
                exit_time = timestamps[j]
                exit_reason = 'TIMEOUT'

            pnl_pct = (exit_price - entry_price) / entry_price * 100

            trades.append({
                'entry_time': entry_time,
                'entry_price': entry_price,
                'tp_price': tp_price,
                'sl_price': sl_price,
                'exit_time': exit_time,
                'exit_price': exit_price,
                'exit_reason': exit_reason,
                'pnl_pct': pnl_pct,
            })
            i = j + 1
        else:
            i += 1

    return trades


def analyze_all_strategies():
    """分析所有策略的真实表现"""
    print("=" * 80)
    print("真实回测分析系统")
    print("=" * 80)

    data = load_data()
    timeframes = ['1w', '1d', '4h', '1h']

    # 参数范围
    tp_range = [20, 30, 50, 75, 100, 150, 200]
    sl_range = [2, 3, 5, 7, 10, 15]
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

            best_result = None
            best_ev = -float('inf')

            for tp in tp_range:
                for sl in sl_range:
                    if tp / sl < 2:  # 至少2:1盈亏比
                        continue

                    trades = real_backtest(df, signal_arr, tp, sl, hold_bars=100)

                    if len(trades) < 2:
                        continue

                    # 计算真实统计
                    total = len(trades)
                    tp_wins = sum(1 for t in trades if t['exit_reason'] == 'TP')
                    sl_losses = sum(1 for t in trades if t['exit_reason'] == 'SL')
                    timeouts = sum(1 for t in trades if t['exit_reason'] == 'TIMEOUT')
                    timeout_wins = sum(1 for t in trades if t['exit_reason'] == 'TIMEOUT' and t['pnl_pct'] > 0)

                    wins = tp_wins + timeout_wins
                    win_rate = wins / total * 100

                    for lev in lev_range:
                        if sl * lev >= 90:
                            continue

                        ev = (win_rate/100 * tp * lev) - ((1 - win_rate/100) * sl * lev)

                        if ev > best_ev:
                            best_ev = ev
                            best_result = {
                                'strategy': strategy_name,
                                'timeframe': tf,
                                'tp': tp,
                                'sl': sl,
                                'leverage': lev,
                                'trades': total,
                                'tp_wins': tp_wins,
                                'sl_losses': sl_losses,
                                'timeouts': timeouts,
                                'timeout_wins': timeout_wins,
                                'total_wins': wins,
                                'win_rate': win_rate,
                                'ev': ev,
                                'trade_details': trades,
                            }

            if best_result:
                all_results.append(best_result)
                print(f"  {strategy_name}: 交易={best_result['trades']} 止盈={best_result['tp_wins']} 止损={best_result['sl_losses']} 胜率={best_result['win_rate']:.1f}% EV={best_result['ev']:.1f}%")

    return all_results


def generate_html_report(results):
    """生成HTML报告"""

    # 按EV排序
    results_sorted = sorted(results, key=lambda x: x['ev'], reverse=True)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 真实回测策略报告</title>
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
        .warning {{
            background: rgba(220, 38, 38, 0.2);
            border: 2px solid #dc2626;
            border-radius: 10px;
            padding: 15px;
            margin: 20px 0;
            text-align: center;
        }}
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
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.85em; }}
        th {{
            background: rgba(255, 215, 0, 0.2);
            color: #ffd700;
            padding: 10px 6px;
            text-align: left;
        }}
        td {{ padding: 8px 6px; border-bottom: 1px solid rgba(255,255,255,0.1); }}
        tr:hover {{ background: rgba(255,215,0,0.05); }}
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
        .ev-high {{ color: #4ade80; font-weight: bold; }}
        .ev-low {{ color: #f97316; }}
        .ev-negative {{ color: #dc2626; }}
        .win {{ color: #4ade80; }}
        .loss {{ color: #dc2626; }}
        .trade-detail {{
            background: rgba(0,0,0,0.2);
            border-radius: 8px;
            padding: 15px;
            margin: 10px 0;
            font-size: 0.85em;
        }}
        .highlight {{ background: linear-gradient(90deg, rgba(255,215,0,0.1), transparent); }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 真实回测策略报告</h1>

        <div class="warning">
            <strong>重要说明:</strong> 本报告中所有胜率数据均经过真实K线回测验证，
            严格执行止盈止损，止损优先于止盈触发。
        </div>

        <div class="section">
            <h2>Top 30 最优EV策略 (真实回测)</h2>
            <table>
                <tr>
                    <th>#</th>
                    <th>策略</th>
                    <th>周期</th>
                    <th>TP%</th>
                    <th>SL%</th>
                    <th>杠杆</th>
                    <th>总交易</th>
                    <th>止盈触发</th>
                    <th>止损触发</th>
                    <th>超时平仓</th>
                    <th>胜率</th>
                    <th>EV%</th>
                </tr>
"""

    for i, r in enumerate(results_sorted[:30], 1):
        tf_class = f"badge-{r['timeframe']}"
        ev_class = 'ev-high' if r['ev'] > 500 else 'ev-low' if r['ev'] > 0 else 'ev-negative'
        highlight = 'highlight' if i <= 5 else ''

        html += f"""
                <tr class="{highlight}">
                    <td>{i}</td>
                    <td>{r['strategy']}</td>
                    <td><span class="badge {tf_class}">{r['timeframe']}</span></td>
                    <td>{r['tp']}%</td>
                    <td>{r['sl']}%</td>
                    <td>{r['leverage']}x</td>
                    <td>{r['trades']}</td>
                    <td class="win">{r['tp_wins']}</td>
                    <td class="loss">{r['sl_losses']}</td>
                    <td>{r['timeouts']}</td>
                    <td>{r['win_rate']:.1f}%</td>
                    <td class="{ev_class}">{r['ev']:.1f}%</td>
                </tr>"""

    html += """
            </table>
        </div>
"""

    # 每个周期的Top 5
    for tf in ['1w', '1d', '4h', '1h']:
        tf_results = [r for r in results_sorted if r['timeframe'] == tf][:5]
        if not tf_results:
            continue

        tf_name = {'1w': '周线', '1d': '日线', '4h': '4小时', '1h': '1小时'}[tf]

        html += f"""
        <div class="section">
            <h2>{tf_name} ({tf}) Top 5 策略及详细交易记录</h2>
"""

        for rank, r in enumerate(tf_results, 1):
            html += f"""
            <h3>{rank}. {r['strategy']} (EV: {r['ev']:.1f}%)</h3>
            <p>参数: TP={r['tp']}% SL={r['sl']}% 杠杆={r['leverage']}x |
               交易={r['trades']} 止盈={r['tp_wins']} 止损={r['sl_losses']} 超时={r['timeouts']} |
               胜率={r['win_rate']:.1f}%</p>
            <div class="trade-detail">
                <table>
                    <tr>
                        <th>#</th>
                        <th>入场时间</th>
                        <th>入场价</th>
                        <th>止盈价</th>
                        <th>止损价</th>
                        <th>出场价</th>
                        <th>出场原因</th>
                        <th>盈亏%</th>
                    </tr>
"""
            for j, t in enumerate(r['trade_details'][:20], 1):  # 最多显示20笔
                entry_time = pd.Timestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M')
                reason_cn = {'TP': '止盈', 'SL': '止损', 'TIMEOUT': '超时'}.get(t['exit_reason'], t['exit_reason'])
                pnl_class = 'win' if t['pnl_pct'] > 0 else 'loss'

                html += f"""
                    <tr>
                        <td>{j}</td>
                        <td>{entry_time}</td>
                        <td>${t['entry_price']:,.0f}</td>
                        <td>${t['tp_price']:,.0f}</td>
                        <td>${t['sl_price']:,.0f}</td>
                        <td>${t['exit_price']:,.0f}</td>
                        <td>{reason_cn}</td>
                        <td class="{pnl_class}">{t['pnl_pct']:+.2f}%</td>
                    </tr>"""

            if len(r['trade_details']) > 20:
                html += f"""
                    <tr><td colspan="8" style="text-align:center; color:#888;">... 还有 {len(r['trade_details'])-20} 笔交易 ...</td></tr>"""

            html += """
                </table>
            </div>
"""

        html += """
        </div>
"""

    # 策略条件说明
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

        <div style="text-align: center; color: #666; margin-top: 30px; padding: 20px;">
            <p>EV公式: E(R) = (胜率 × 止盈% × 杠杆) - ((1-胜率) × 止损% × 杠杆)</p>
            <p>所有数据经过真实K线回测验证 | 数据来源: Binance BTCUSDT 2019-09 至 2025-11</p>
            <p>生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>
        </div>
    </div>
</body>
</html>
"""

    with open('../reports/真实回测策略报告.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告已保存: ../reports/真实回测策略报告.html")


def main():
    results = analyze_all_strategies()

    if results:
        # 保存CSV
        csv_data = [{k: v for k, v in r.items() if k != 'trade_details'} for r in results]
        df = pd.DataFrame(csv_data)
        df.to_csv('../reports/真实回测结果.csv', index=False)
        print(f"\nCSV已保存: ../reports/真实回测结果.csv")

        # 生成HTML报告
        generate_html_report(results)

    return results


if __name__ == "__main__":
    results = main()
