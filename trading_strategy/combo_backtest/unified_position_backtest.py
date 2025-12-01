#!/usr/bin/env python3
"""
BTC/USDT 全局仓位管理回测
- 同一时间只能有一个持仓
- 已持仓时，其他策略信号忽略
- 移动止盈止损继续运行
- 平仓后才能接受新的开仓信号
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')

from comprehensive_backtest import load_data, add_all_indicators, get_combo_signals, STRATEGY_DESCRIPTIONS


class Position:
    """持仓对象"""
    def __init__(self, strategy_name, entry_bar, entry_price, entry_time,
                 tp_pct, sl_pct, trail_pct, leverage):
        self.strategy_name = strategy_name
        self.entry_bar = entry_bar
        self.entry_price = entry_price
        self.entry_time = entry_time
        self.tp_pct = tp_pct
        self.sl_pct = sl_pct
        self.trail_pct = trail_pct
        self.leverage = leverage

        # 止盈止损价格
        self.tp_price = entry_price * (1 + tp_pct / 100)
        self.initial_sl_price = entry_price * (1 - sl_pct / 100)
        self.current_sl_price = self.initial_sl_price
        self.highest_price = entry_price

        # 出场信息
        self.exit_bar = None
        self.exit_price = None
        self.exit_time = None
        self.exit_reason = None
        self.pnl_pct = None

    def update_trailing_stop(self, high_price):
        """更新移动止损"""
        if high_price > self.highest_price:
            self.highest_price = high_price
            if self.trail_pct > 0:
                new_trail_sl = self.highest_price * (1 - self.trail_pct / 100)
                if new_trail_sl > self.current_sl_price:
                    self.current_sl_price = new_trail_sl

    def check_exit(self, bar_idx, high, low, close, timestamp, hold_bars=100):
        """检查是否触发出场条件"""
        # 更新移动止损
        self.update_trailing_stop(high)

        # 检查止损 (优先)
        if low <= self.current_sl_price:
            self.exit_bar = bar_idx
            self.exit_price = self.current_sl_price
            self.exit_time = timestamp
            if self.current_sl_price > self.initial_sl_price:
                self.exit_reason = 'TRAIL_SL'  # 移动止损 (保本或盈利)
            else:
                self.exit_reason = 'SL'  # 初始止损
            self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price * 100
            return True

        # 检查止盈
        if high >= self.tp_price:
            self.exit_bar = bar_idx
            self.exit_price = self.tp_price
            self.exit_time = timestamp
            self.exit_reason = 'TP'
            self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price * 100
            return True

        # 检查超时
        if bar_idx - self.entry_bar >= hold_bars:
            self.exit_bar = bar_idx
            self.exit_price = close
            self.exit_time = timestamp
            self.exit_reason = 'TIMEOUT'
            self.pnl_pct = (self.exit_price - self.entry_price) / self.entry_price * 100
            return True

        return False

    def to_dict(self):
        """转为字典"""
        return {
            'strategy': self.strategy_name,
            'entry_time': self.entry_time,
            'entry_price': self.entry_price,
            'tp_price': self.tp_price,
            'initial_sl': self.initial_sl_price,
            'final_sl': self.current_sl_price,
            'highest_price': self.highest_price,
            'exit_time': self.exit_time,
            'exit_price': self.exit_price,
            'exit_reason': self.exit_reason,
            'pnl_pct': self.pnl_pct,
            'tp_pct': self.tp_pct,
            'sl_pct': self.sl_pct,
            'trail_pct': self.trail_pct,
            'leverage': self.leverage,
        }


def unified_backtest(df, all_signals, tp_pct, sl_pct, trail_pct, leverage, hold_bars=100):
    """
    全局仓位管理回测

    参数:
        df: K线数据
        all_signals: dict, {策略名: 信号数组}
        tp_pct: 止盈百分比
        sl_pct: 止损百分比
        trail_pct: 移动止损回撤百分比 (0表示不使用移动止损)
        leverage: 杠杆倍数
        hold_bars: 最大持仓K线数

    返回:
        trades: 所有交易记录
        stats: 统计信息
    """
    close_arr = df['close'].values
    high_arr = df['high'].values
    low_arr = df['low'].values
    timestamps = df['timestamp'].values

    n = len(df)
    warmup = min(250, n // 4)

    trades = []
    current_position = None

    # 记录每个策略的信号触发次数和实际开仓次数
    strategy_stats = {name: {'signals': 0, 'opened': 0} for name in all_signals.keys()}

    i = warmup
    while i < n:
        if current_position is None:
            # 没有持仓，检查所有策略信号
            # 按策略优先级检查（可以根据EV排序）
            for strategy_name, signal_arr in all_signals.items():
                if signal_arr[i]:
                    strategy_stats[strategy_name]['signals'] += 1

                    # 开新仓位
                    current_position = Position(
                        strategy_name=strategy_name,
                        entry_bar=i,
                        entry_price=close_arr[i],
                        entry_time=timestamps[i],
                        tp_pct=tp_pct,
                        sl_pct=sl_pct,
                        trail_pct=trail_pct,
                        leverage=leverage
                    )
                    strategy_stats[strategy_name]['opened'] += 1
                    break  # 只开一个仓位

            i += 1
        else:
            # 有持仓，检查是否出场
            exited = current_position.check_exit(
                bar_idx=i,
                high=high_arr[i],
                low=low_arr[i],
                close=close_arr[i],
                timestamp=timestamps[i],
                hold_bars=hold_bars
            )

            if exited:
                trades.append(current_position.to_dict())
                current_position = None

            # 统计被忽略的信号
            for strategy_name, signal_arr in all_signals.items():
                if signal_arr[i] and current_position is not None:
                    strategy_stats[strategy_name]['signals'] += 1
                    # 信号被忽略，因为有持仓

            i += 1

    # 计算统计
    if trades:
        total = len(trades)
        wins = sum(1 for t in trades if t['pnl_pct'] > 0)
        win_rate = wins / total * 100
        total_pnl = sum(t['pnl_pct'] for t in trades)
        avg_pnl = total_pnl / total

        tp_wins = sum(1 for t in trades if t['exit_reason'] == 'TP')
        sl_losses = sum(1 for t in trades if t['exit_reason'] == 'SL')
        trail_exits = sum(1 for t in trades if t['exit_reason'] == 'TRAIL_SL')
        timeouts = sum(1 for t in trades if t['exit_reason'] == 'TIMEOUT')

        # 按策略统计
        by_strategy = {}
        for t in trades:
            s = t['strategy']
            if s not in by_strategy:
                by_strategy[s] = {'trades': 0, 'wins': 0, 'pnl': 0}
            by_strategy[s]['trades'] += 1
            if t['pnl_pct'] > 0:
                by_strategy[s]['wins'] += 1
            by_strategy[s]['pnl'] += t['pnl_pct']

        stats = {
            'total': total,
            'wins': wins,
            'win_rate': win_rate,
            'total_pnl': total_pnl,
            'avg_pnl': avg_pnl,
            'tp_wins': tp_wins,
            'sl_losses': sl_losses,
            'trail_exits': trail_exits,
            'timeouts': timeouts,
            'by_strategy': by_strategy,
            'strategy_stats': strategy_stats,
        }
    else:
        stats = None

    return trades, stats


def run_unified_backtest():
    """运行全局仓位管理回测"""
    print("=" * 80)
    print("BTC/USDT 全局仓位管理回测")
    print("同一时间只持有一个仓位，已持仓时忽略其他信号")
    print("=" * 80)

    data = load_data()
    timeframes = ['1w', '1d', '4h', '1h']

    # 回测参数
    param_sets = [
        {'tp': 50, 'sl': 5, 'trail': 5, 'leverage': 10},
        {'tp': 75, 'sl': 5, 'trail': 5, 'leverage': 10},
        {'tp': 100, 'sl': 5, 'trail': 5, 'leverage': 10},
        {'tp': 50, 'sl': 5, 'trail': 10, 'leverage': 10},
        {'tp': 75, 'sl': 5, 'trail': 10, 'leverage': 10},
        {'tp': 100, 'sl': 5, 'trail': 10, 'leverage': 10},
        {'tp': 50, 'sl': 3, 'trail': 5, 'leverage': 15},
        {'tp': 75, 'sl': 3, 'trail': 5, 'leverage': 15},
    ]

    all_results = []

    for tf in timeframes:
        if tf not in data:
            continue

        print(f"\n{'='*60}")
        print(f"时间周期: {tf}")
        print(f"{'='*60}")

        df = add_all_indicators(data[tf], data['fear_greed'], data['funding'])
        all_signals = get_combo_signals(df)

        # 过滤掉信号太少的策略
        valid_signals = {k: v for k, v in all_signals.items() if np.sum(v) >= 2}
        print(f"有效策略数: {len(valid_signals)}")

        for params in param_sets:
            tp, sl, trail, lev = params['tp'], params['sl'], params['trail'], params['leverage']

            trades, stats = unified_backtest(
                df, valid_signals, tp, sl, trail, lev, hold_bars=100
            )

            if stats and stats['total'] >= 3:
                ev = (stats['win_rate']/100 * tp * lev) - ((1 - stats['win_rate']/100) * sl * lev)

                result = {
                    'timeframe': tf,
                    'tp': tp,
                    'sl': sl,
                    'trail': trail,
                    'leverage': lev,
                    'trades': trades,
                    **stats,
                    'ev': ev,
                }
                all_results.append(result)

                print(f"  TP={tp}% SL={sl}% Trail={trail}% Lev={lev}x | "
                      f"交易={stats['total']} 胜率={stats['win_rate']:.1f}% EV={ev:.0f}%")

    return all_results


def generate_unified_report(results):
    """生成全局仓位管理报告"""

    # 按EV排序
    sorted_results = sorted(results, key=lambda x: x['ev'], reverse=True)

    html = f"""
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 全局仓位管理回测报告</title>
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
        .info-box {{
            background: rgba(31, 111, 235, 0.15);
            border: 2px solid #1f6feb;
            border-radius: 10px;
            padding: 20px;
            margin: 20px 0;
        }}
        .info-box h3 {{ color: #58a6ff; margin-top: 0; }}
        .info-box ul {{ margin: 10px 0; padding-left: 20px; }}
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
        table {{ width: 100%; border-collapse: collapse; margin-top: 15px; font-size: 0.85em; }}
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
            font-size: 0.75em;
            font-weight: bold;
        }}
        .badge-1w {{ background: #da3633; }}
        .badge-1d {{ background: #d29922; }}
        .badge-4h {{ background: #1f6feb; }}
        .badge-1h {{ background: #8957e5; }}
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
            max-height: 500px;
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
        .strategy-breakdown {{
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(250px, 1fr));
            gap: 10px;
            margin: 15px 0;
        }}
        .strategy-card {{
            background: rgba(255,255,255,0.03);
            border-radius: 8px;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.1);
        }}
        .strategy-card .name {{ color: #58a6ff; font-weight: bold; }}
        .strategy-card .stats {{ color: #8b949e; font-size: 0.85em; margin-top: 5px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 全局仓位管理回测报告</h1>

        <div class="info-box">
            <h3>全局仓位管理规则</h3>
            <ul>
                <li><b>单一仓位:</b> 同一时间最多只能持有一个BTC仓位</li>
                <li><b>信号处理:</b> 当A策略开仓后，B策略信号会被忽略，直到A策略平仓</li>
                <li><b>移动止损:</b> 持仓期间移动止盈止损正常运行，锁定利润</li>
                <li><b>策略优先:</b> 同一根K线多个策略触发时，按策略顺序优先开仓</li>
            </ul>
        </div>
"""

    # 总体统计
    total_trades = sum(r['total'] for r in results)
    total_wins = sum(r['wins'] for r in results)
    overall_wr = total_wins / total_trades * 100 if total_trades > 0 else 0
    best_ev = max(r['ev'] for r in results) if results else 0

    html += f"""
        <div class="stats-grid">
            <div class="stat-card">
                <div class="stat-value">{len(results)}</div>
                <div class="stat-label">参数组合数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_trades}</div>
                <div class="stat-label">总交易次数</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{overall_wr:.1f}%</div>
                <div class="stat-label">综合胜率</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{best_ev:.0f}%</div>
                <div class="stat-label">最高EV</div>
            </div>
        </div>
"""

    # 参数组合排名
    html += """
        <div class="section">
            <h2>参数组合排名 (按EV)</h2>
            <table>
                <tr>
                    <th>#</th>
                    <th>周期</th>
                    <th>TP%</th>
                    <th>SL%</th>
                    <th>移动%</th>
                    <th>杠杆</th>
                    <th>交易数</th>
                    <th>止盈</th>
                    <th>止损</th>
                    <th>移动出</th>
                    <th>超时</th>
                    <th>胜率</th>
                    <th>总盈亏%</th>
                    <th>EV%</th>
                </tr>
"""

    for i, r in enumerate(sorted_results, 1):
        tf_class = f"badge-{r['timeframe']}"
        ev_class = 'ev-high' if r['ev'] > 500 else 'ev-medium' if r['ev'] > 200 else 'ev-low'
        highlight = 'highlight' if i <= 3 else ''

        html += f"""
                <tr class="{highlight}">
                    <td>{i}</td>
                    <td><span class="badge {tf_class}">{r['timeframe']}</span></td>
                    <td>{r['tp']}%</td>
                    <td>{r['sl']}%</td>
                    <td>{r['trail']}%</td>
                    <td>{r['leverage']}x</td>
                    <td>{r['total']}</td>
                    <td class="win">{r['tp_wins']}</td>
                    <td class="loss">{r['sl_losses']}</td>
                    <td>{r['trail_exits']}</td>
                    <td>{r['timeouts']}</td>
                    <td>{r['win_rate']:.1f}%</td>
                    <td>{r['total_pnl']:.1f}%</td>
                    <td class="{ev_class}">{r['ev']:.0f}%</td>
                </tr>"""

    html += """
            </table>
        </div>
"""

    # 每个周期的详细结果
    for tf in ['1w', '1d', '4h', '1h']:
        tf_results = [r for r in sorted_results if r['timeframe'] == tf]
        if not tf_results:
            continue

        tf_name = {'1w': '周线', '1d': '日线', '4h': '4小时', '1h': '1小时'}[tf]
        best = tf_results[0]  # 已排序，第一个是EV最高的

        html += f"""
        <div class="section">
            <h2>{tf_name} ({tf}) 最优参数详情</h2>
            <p><b>最优参数:</b> TP={best['tp']}% SL={best['sl']}% 移动={best['trail']}% 杠杆={best['leverage']}x</p>
            <p><b>统计:</b> 交易={best['total']} 胜率={best['win_rate']:.1f}% EV={best['ev']:.0f}%</p>

            <h3>策略贡献分布</h3>
            <div class="strategy-breakdown">
"""

        # 显示每个策略的贡献
        if 'by_strategy' in best:
            for strat_name, strat_stats in sorted(best['by_strategy'].items(),
                                                   key=lambda x: x[1]['trades'],
                                                   reverse=True):
                strat_wr = strat_stats['wins'] / strat_stats['trades'] * 100 if strat_stats['trades'] > 0 else 0
                pnl_class = 'win' if strat_stats['pnl'] > 0 else 'loss'

                html += f"""
                <div class="strategy-card">
                    <div class="name">{strat_name}</div>
                    <div class="stats">
                        交易: {strat_stats['trades']} |
                        胜率: {strat_wr:.0f}% |
                        盈亏: <span class="{pnl_class}">{strat_stats['pnl']:.1f}%</span>
                    </div>
                </div>"""

        html += """
            </div>

            <h3>详细交易记录</h3>
            <div class="trade-box">
                <table>
                    <tr>
                        <th>#</th>
                        <th>策略</th>
                        <th>入场时间</th>
                        <th>入场价</th>
                        <th>止盈价</th>
                        <th>初始止损</th>
                        <th>最终止损</th>
                        <th>最高价</th>
                        <th>出场价</th>
                        <th>出场原因</th>
                        <th>盈亏%</th>
                    </tr>
"""

        for j, t in enumerate(best['trades'][:50], 1):  # 最多50笔
            entry_time = pd.Timestamp(t['entry_time']).strftime('%Y-%m-%d %H:%M')
            reason_map = {
                'TP': '止盈',
                'SL': '止损',
                'TRAIL_SL': '移动止损',
                'TIMEOUT': '超时'
            }
            reason_cn = reason_map.get(t['exit_reason'], t['exit_reason'])
            pnl_class = 'win' if t['pnl_pct'] > 0 else 'loss'

            html += f"""
                    <tr>
                        <td>{j}</td>
                        <td>{t['strategy'][:15]}</td>
                        <td>{entry_time}</td>
                        <td>${t['entry_price']:,.0f}</td>
                        <td>${t['tp_price']:,.0f}</td>
                        <td>${t['initial_sl']:,.0f}</td>
                        <td>${t['final_sl']:,.0f}</td>
                        <td>${t['highest_price']:,.0f}</td>
                        <td>${t['exit_price']:,.0f}</td>
                        <td>{reason_cn}</td>
                        <td class="{pnl_class}">{t['pnl_pct']:+.2f}%</td>
                    </tr>"""

        if len(best['trades']) > 50:
            html += f"""
                    <tr><td colspan="11" style="text-align:center; color:#8b949e;">
                        ... 还有 {len(best['trades'])-50} 笔交易 ...
                    </td></tr>"""

        html += """
                </table>
            </div>
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
            <h2>全局仓位管理说明</h2>
            <ul>
                <li><b>为什么需要全局仓位管理?</b> 避免多个策略同时开仓导致仓位过重、资金占用过高</li>
                <li><b>信号优先级:</b> 当多个策略同时触发时，按代码中的策略顺序优先开仓</li>
                <li><b>信号统计:</b> 部分信号会因为已有持仓而被忽略，这是正常现象</li>
                <li><b>移动止损:</b> 持仓期间价格创新高时，止损价会跟随上移，锁定利润</li>
                <li><b>EV计算:</b> EV = (胜率 × 止盈% × 杠杆) - ((1-胜率) × 止损% × 杠杆)</li>
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

    with open('../reports/全局仓位管理回测报告.html', 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"\n报告已保存: ../reports/全局仓位管理回测报告.html")


def main():
    results = run_unified_backtest()

    if results:
        # 保存CSV
        csv_data = []
        for r in results:
            row = {k: v for k, v in r.items() if k not in ['trades', 'by_strategy', 'strategy_stats']}
            csv_data.append(row)
        df = pd.DataFrame(csv_data)
        df.to_csv('../reports/全局仓位管理回测结果.csv', index=False)
        print(f"\nCSV已保存: ../reports/全局仓位管理回测结果.csv")

        # 生成HTML报告
        generate_unified_report(results)

    return results


if __name__ == "__main__":
    results = main()
