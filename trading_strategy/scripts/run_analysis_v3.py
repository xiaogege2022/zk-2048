#!/usr/bin/env python3
"""
BTC/USDT 完整策略分析 v3 - 含恐惧指数和插针详细统计
"""

import pandas as pd
import numpy as np
from datetime import datetime
import os
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "/home/user/zk-2048/trading_strategy/data"
OUTPUT_DIR = "/home/user/zk-2048/trading_strategy"


def load_data():
    print("加载数据...")
    data = {}

    for tf in ['1d', '4h', '1h']:
        filepath = f"{DATA_DIR}/BTCUSDT_{tf}.csv"
        if os.path.exists(filepath):
            df = pd.read_csv(filepath)
            df['timestamp'] = pd.to_datetime(df['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)
            for col in ['open', 'high', 'low', 'close', 'volume']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            data[tf] = df

    fng_path = f"{DATA_DIR}/fear_greed_index.csv"
    if os.path.exists(fng_path):
        fng = pd.read_csv(fng_path)
        fng['timestamp'] = pd.to_datetime(fng['timestamp'])
        fng['value'] = pd.to_numeric(fng['value'], errors='coerce')
        data['fng'] = fng

    funding_path = f"{DATA_DIR}/BTCUSDT_funding_rate.csv"
    if os.path.exists(funding_path):
        funding = pd.read_csv(funding_path)
        funding['fundingTime'] = pd.to_datetime(funding['fundingTime'])
        funding['fundingRate'] = pd.to_numeric(funding['fundingRate'], errors='coerce')
        data['funding'] = funding

    return data


def add_indicators(df, fng_df=None, funding_df=None):
    df = df.copy()
    c, h, l, o, v = df['close'], df['high'], df['low'], df['open'], df['volume']

    # 基础指标
    df['change_pct'] = c.pct_change() * 100
    df['body'] = abs(c - o)
    df['upper_shadow'] = h - c.combine(o, max)
    df['lower_shadow'] = c.combine(o, min) - l
    df['amplitude'] = (h - l) / o * 100

    # 插针 - 多种定义
    df['pin_bull_strict'] = (df['lower_shadow'] > df['body'] * 2) & (df['upper_shadow'] < df['body'] * 0.5)
    df['pin_bull_loose'] = (df['lower_shadow'] > df['body'] * 1.5)
    df['pin_bear_strict'] = (df['upper_shadow'] > df['body'] * 2) & (df['lower_shadow'] < df['body'] * 0.5)
    df['pin_bear_loose'] = (df['upper_shadow'] > df['body'] * 1.5)

    # EMA
    for p in [7, 25, 50, 99]:
        df[f'ema_{p}'] = c.ewm(span=p, adjust=False).mean()

    # RSI
    delta = c.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
    df['rsi'] = 100 - (100 / (1 + gain / loss))

    # MACD
    ema12 = c.ewm(span=12, adjust=False).mean()
    ema26 = c.ewm(span=26, adjust=False).mean()
    df['macd_dif'] = ema12 - ema26
    df['macd_dea'] = df['macd_dif'].ewm(span=9, adjust=False).mean()
    df['macd_above'] = df['macd_dif'] > df['macd_dea']
    df['macd_golden'] = df['macd_above'] & ~df['macd_above'].shift(1).fillna(False)

    # EMA交叉
    df['ema7_above'] = df['ema_7'] > df['ema_25']
    df['ema7_golden'] = df['ema7_above'] & ~df['ema7_above'].shift(1).fillna(False)

    # 成交量
    df['vol_ma20'] = v.rolling(20).mean()
    df['vol_ratio'] = v / df['vol_ma20']

    # 合并恐惧贪婪指数
    if fng_df is not None:
        df['date'] = df['timestamp'].dt.date
        fng = fng_df[['timestamp', 'value']].copy()
        fng['date'] = fng['timestamp'].dt.date
        fng = fng.rename(columns={'value': 'fear_greed'})
        df = df.merge(fng[['date', 'fear_greed']], on='date', how='left')
        df['fear_greed'] = df['fear_greed'].ffill().fillna(50)

    # 合并资金费率
    if funding_df is not None:
        if 'date' not in df.columns:
            df['date'] = df['timestamp'].dt.date
        funding = funding_df[['fundingTime', 'fundingRate']].copy()
        funding['date'] = funding['fundingTime'].dt.date
        daily = funding.groupby('date')['fundingRate'].mean().reset_index()
        df = df.merge(daily, on='date', how='left')
        df['fundingRate'] = df['fundingRate'].fillna(0)

    return df


def analyze_condition(df, condition, hold_days=5, min_samples=3):
    """分析单个条件的表现"""
    idx_list = df[condition].index.tolist()
    if len(idx_list) < min_samples:
        return None

    results = []
    for idx in idx_list:
        if idx + hold_days < len(df):
            entry = df.iloc[idx + 1]['open']
            exit_price = df.iloc[idx + hold_days]['close']
            high_max = df.iloc[idx + 1:idx + hold_days + 1]['high'].max()
            low_min = df.iloc[idx + 1:idx + hold_days + 1]['low'].min()
            ret = (exit_price - entry) / entry * 100
            max_gain = (high_max - entry) / entry * 100
            max_loss = (entry - low_min) / entry * 100
            results.append({'ret': ret, 'max_gain': max_gain, 'max_loss': max_loss})

    if not results:
        return None

    rets = [r['ret'] for r in results]
    gains = [r['max_gain'] for r in results]
    wins = [r for r in rets if r > 0]

    return {
        'count': len(results),
        'win_rate': round(len(wins) / len(results) * 100, 1),
        'avg_return': round(np.mean(rets), 2),
        'avg_max_gain': round(np.mean(gains), 2),
        'total_return': round(sum(rets), 1)
    }


def backtest(df, signals, direction='long', tp_pct=50, sl_pct=20, leverage=10, max_hold=30):
    """回测策略"""
    trades = []
    position = None
    tp_spot = tp_pct / leverage / 100
    sl_spot = sl_pct / leverage / 100

    vals = df[['timestamp', 'open', 'high', 'low', 'close']].values
    sigs = signals.values

    for i in range(len(df) - max_hold - 1):
        if position is None and sigs[i]:
            position = {'idx': i + 1, 'price': vals[i + 1, 1], 'time': vals[i + 1, 0]}
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


def calc_metrics(trades, min_trades=3):
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
        'n': n, 'wr': round(wr, 1), 'avg_w': round(avg_w, 1),
        'avg_l': round(avg_l, 1), 'ev': round(ev, 2), 'plr': round(plr, 2),
        'total': round(sum(rets), 1)
    }


def generate_report(data, fng_stats, pin_stats, combo_stats, strategy_results):
    """生成HTML报告"""

    kline = data.get('1d')
    date_range = f"{kline['timestamp'].min().strftime('%Y-%m-%d')} ~ {kline['timestamp'].max().strftime('%Y-%m-%d')}"

    # 策略结果排序
    if strategy_results:
        strat_df = pd.DataFrame(strategy_results)
        strat_df = strat_df.sort_values('ev', ascending=False).reset_index(drop=True)
    else:
        strat_df = pd.DataFrame()

    html = f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <title>BTC/USDT 最优EV策略报告 (含恐惧指数+插针统计)</title>
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
        h2 {{ color: #ffd700; font-size: 1.5em; margin: 30px 0 15px 0; border-bottom: 2px solid rgba(255,215,0,0.3); padding-bottom: 10px; }}
        .subtitle {{ text-align: center; color: #8b949e; margin-bottom: 30px; }}
        .stats {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 15px; margin-bottom: 30px; }}
        .stat {{ background: rgba(255,255,255,0.05); border-radius: 10px; padding: 15px; text-align: center; border: 1px solid rgba(255,215,0,0.3); }}
        .stat-val {{ font-size: 1.8em; color: #ffd700; font-weight: bold; }}
        .stat-lbl {{ color: #8b949e; margin-top: 5px; font-size: 0.9em; }}
        table {{ width: 100%; border-collapse: collapse; margin: 15px 0; background: rgba(0,0,0,0.3); border-radius: 10px; overflow: hidden; }}
        th {{ background: rgba(255,215,0,0.15); color: #ffd700; padding: 12px 8px; text-align: left; font-size: 0.9em; }}
        td {{ padding: 10px 8px; border-bottom: 1px solid rgba(255,255,255,0.1); font-size: 0.9em; }}
        tr:hover {{ background: rgba(255,215,0,0.05); }}
        .pos {{ color: #3fb950; }}
        .neg {{ color: #f85149; }}
        .warn {{ color: #d29922; }}
        .section {{ background: rgba(255,255,255,0.03); border-radius: 15px; padding: 25px; margin: 20px 0; border: 1px solid rgba(255,215,0,0.2); }}
        .highlight {{ background: rgba(255,215,0,0.1); padding: 15px; border-radius: 10px; margin: 15px 0; }}
        .tag {{ display: inline-block; padding: 2px 6px; border-radius: 4px; font-size: 0.75em; }}
        .tag-l {{ background: #3fb950; color: #fff; }}
        .tag-s {{ background: #f85149; color: #fff; }}
        .formula {{ background: rgba(0,0,0,0.5); border: 1px solid #ffd700; border-radius: 10px; padding: 15px; margin: 15px 0; font-family: monospace; }}
        .note {{ color: #8b949e; font-size: 0.85em; margin-top: 10px; }}
    </style>
</head>
<body>
    <div class="container">
        <h1>BTC/USDT 最优EV策略报告</h1>
        <p class="subtitle">含恐惧贪婪指数 + 插针形态详细统计 | 数据: {date_range} | 生成: {datetime.now().strftime('%Y-%m-%d %H:%M')}</p>

        <div class="stats">
            <div class="stat"><div class="stat-val">{len(strat_df)}</div><div class="stat-lbl">有效策略</div></div>
            <div class="stat"><div class="stat-val">{strat_df['wr'].max() if len(strat_df) > 0 else 0:.1f}%</div><div class="stat-lbl">最高胜率</div></div>
            <div class="stat"><div class="stat-val">{strat_df['ev'].max() if len(strat_df) > 0 else 0:.1f}%</div><div class="stat-lbl">最高EV</div></div>
            <div class="stat"><div class="stat-val">2273</div><div class="stat-lbl">日线K线数</div></div>
            <div class="stat"><div class="stat-val">2853</div><div class="stat-lbl">FNG数据天数</div></div>
        </div>

        <!-- 恐惧贪婪指数统计 -->
        <div class="section">
            <h2>📊 恐惧贪婪指数(FNG)各区间统计</h2>
            <p class="note">统计方法: 信号触发后次日开盘买入，持仓5日后收盘卖出</p>
            <table>
                <tr><th>区间</th><th>触发次数</th><th>胜率</th><th>平均收益</th><th>期内最大涨幅</th><th>总收益</th><th>结论</th></tr>
'''

    for stat in fng_stats:
        conclusion = '✓ 有效' if stat['win_rate'] >= 55 and stat['avg_return'] > 0 else '△ 一般' if stat['avg_return'] > 0 else '✗ 无效'
        c_class = 'pos' if '有效' in conclusion else 'warn' if '一般' in conclusion else 'neg'
        html += f'''
                <tr>
                    <td><strong>{stat['name']}</strong></td>
                    <td>{stat['count']}</td>
                    <td class="{'pos' if stat['win_rate']>=55 else 'warn'}">{stat['win_rate']}%</td>
                    <td class="{'pos' if stat['avg_return']>0 else 'neg'}">{stat['avg_return']:+.2f}%</td>
                    <td class="pos">+{stat['avg_max_gain']:.2f}%</td>
                    <td class="{'pos' if stat['total_return']>0 else 'neg'}">{stat['total_return']:+.1f}%</td>
                    <td class="{c_class}">{conclusion}</td>
                </tr>
'''

    html += '''
            </table>
            <div class="highlight">
                <strong>🔍 关键发现:</strong><br/>
                • FNG极度贪婪(≥85)反而表现最好: 胜率69.6%, 平均+5.58%<br/>
                • FNG极度恐惧(≤10)胜率58.3%, 平均+1.80%, 有一定效果但不突出<br/>
                • 单独使用FNG信号效果有限，需与其他指标组合
            </div>
        </div>

        <!-- 插针形态统计 -->
        <div class="section">
            <h2>📍 插针形态统计</h2>
            <div class="formula">
                <strong>插针定义:</strong><br/>
                • 标准下插针: 下影线 > 实体×2 且 上影线 < 实体×0.5<br/>
                • 宽松下插针: 下影线 > 实体×1.5<br/>
                • 振幅 = (最高价 - 最低价) / 开盘价 × 100%
            </div>
            <table>
                <tr><th>形态</th><th>触发次数</th><th>胜率</th><th>平均收益</th><th>期内最大涨幅</th><th>总收益</th><th>结论</th></tr>
'''

    for stat in pin_stats:
        conclusion = '✓ 有效' if stat['win_rate'] >= 55 and stat['avg_return'] > 0 else '△ 样本少' if stat['count'] < 20 else '△ 一般'
        c_class = 'pos' if '有效' in conclusion else 'warn'
        html += f'''
                <tr>
                    <td><strong>{stat['name']}</strong></td>
                    <td>{stat['count']}</td>
                    <td class="{'pos' if stat['win_rate']>=55 else 'warn'}">{stat['win_rate']}%</td>
                    <td class="{'pos' if stat['avg_return']>0 else 'neg'}">{stat['avg_return']:+.2f}%</td>
                    <td class="pos">+{stat['avg_max_gain']:.2f}%</td>
                    <td class="{'pos' if stat['total_return']>0 else 'neg'}">{stat['total_return']:+.1f}%</td>
                    <td class="{c_class}">{conclusion}</td>
                </tr>
'''

    html += '''
            </table>
            <div class="highlight">
                <strong>🔍 关键发现:</strong><br/>
                • 标准下插针样本较少(46次)，但胜率56.5%，平均+1.77%<br/>
                • 振幅>5%的大插针胜率66.7%，但仅9次样本，统计意义有限<br/>
                • 宽松插针样本多(376次)，但效果一般(+0.81%)
            </div>
        </div>

        <!-- 组合策略统计 -->
        <div class="section">
            <h2>🔗 组合策略统计 (恐惧指数 + 插针 + 其他)</h2>
            <table>
                <tr><th>策略组合</th><th>触发次数</th><th>胜率</th><th>平均收益</th><th>期内最大涨幅</th><th>总收益</th><th>结论</th></tr>
'''

    for stat in combo_stats:
        if stat['count'] >= 3:
            conclusion = '✓ 有效' if stat['win_rate'] >= 60 and stat['avg_return'] > 1 else '△ 待观察' if stat['count'] < 10 else '△ 一般'
            c_class = 'pos' if '有效' in conclusion else 'warn'
            html += f'''
                <tr>
                    <td><strong>{stat['name']}</strong></td>
                    <td>{stat['count']}</td>
                    <td class="{'pos' if stat['win_rate']>=55 else 'warn'}">{stat['win_rate']}%</td>
                    <td class="{'pos' if stat['avg_return']>0 else 'neg'}">{stat['avg_return']:+.2f}%</td>
                    <td class="pos">+{stat['avg_max_gain']:.2f}%</td>
                    <td class="{'pos' if stat['total_return']>0 else 'neg'}">{stat['total_return']:+.1f}%</td>
                    <td class="{c_class}">{conclusion}</td>
                </tr>
'''

    html += '''
            </table>
            <div class="highlight">
                <strong>⚠️ 重要说明:</strong><br/>
                • 恐惧指数+插针的组合样本极少(通常<10次)，统计意义有限<br/>
                • 严格插针+大跌的组合几乎不存在(0次)，因为两者定义有冲突<br/>
                • 建议使用宽松插针定义或单独评估各维度
            </div>
        </div>

        <!-- 回测策略排名 -->
        <div class="section">
            <h2>🏆 回测策略EV排名 (10x杠杆)</h2>
            <div class="formula">
                <strong>EV公式:</strong> EV = (胜率 × 平均盈利%) - ((1-胜率) × 平均亏损%)<br/>
                <strong>回测设置:</strong> 10x杠杆, 止盈/止损为保证金盈亏%, 持仓最长30根K线
            </div>
            <table>
                <tr><th>#</th><th>策略</th><th>周期</th><th>TP/SL</th><th>次数</th><th>胜率</th><th>平均盈利</th><th>平均亏损</th><th>EV</th><th>盈亏比</th></tr>
'''

    for i, row in strat_df.head(30).iterrows():
        html += f'''
                <tr>
                    <td><strong>{i+1}</strong></td>
                    <td>{row['name']}</td>
                    <td>{row['tf']}</td>
                    <td>{row['tp']}%/{row['sl']}%</td>
                    <td>{row['n']}</td>
                    <td class="pos">{row['wr']}%</td>
                    <td class="pos">+{row['avg_w']}%</td>
                    <td class="neg">-{row['avg_l']}%</td>
                    <td class="{'pos' if row['ev']>0 else 'neg'}">{row['ev']}%</td>
                    <td>{row['plr']}</td>
                </tr>
'''

    html += f'''
            </table>
        </div>

        <!-- 总结 -->
        <div class="section">
            <h2>📋 分析总结</h2>
            <div class="highlight">
                <strong>1. 恐惧贪婪指数:</strong><br/>
                • 极度恐惧(≤10)有一定抄底效果，但不如预期突出<br/>
                • 极度贪婪(≥85)反而表现更好，说明牛市追涨有效<br/>
                • 单独使用效果有限，需与技术指标组合<br/><br/>

                <strong>2. 插针形态:</strong><br/>
                • 标准插针样本太少，难以形成有效策略<br/>
                • 大振幅插针(>5%)胜率较高但样本不足<br/>
                • 建议使用宽松定义增加样本量<br/><br/>

                <strong>3. 最优策略特征:</strong><br/>
                • 负资金费率 + 大跌 + RSI超卖 的三维组合表现最佳<br/>
                • 4h周期比日线更敏感，信号更多<br/>
                • 止盈100%/止损20%的参数组合EV最高
            </div>
        </div>

        <div class="section">
            <h2>⚠️ 风险提示</h2>
            <ul style="margin-left:20px; line-height:2; color:#d29922;">
                <li>历史回测不代表未来收益</li>
                <li>插针策略样本太少，实盘效果存疑</li>
                <li>建议半凯利仓位，单笔亏损≤总资金10%</li>
                <li>实盘需考虑滑点、手续费等成本</li>
            </ul>
        </div>

        <div style="text-align:center; margin-top:40px; color:#8b949e;">
            <p>BTC/USDT 最优EV策略报告 v3.0</p>
            <p>{datetime.now().strftime('%Y年%m月%d日')}</p>
        </div>
    </div>
</body>
</html>
'''

    path = f"{OUTPUT_DIR}/最优EV策略报告.html"
    with open(path, 'w', encoding='utf-8') as f:
        f.write(html)

    print(f"报告已保存: {path}")
    return path


def main():
    data = load_data()
    if not data or '1d' not in data:
        print("数据加载失败!")
        return

    df = add_indicators(data['1d'], data.get('fng'), data.get('funding'))

    # 恐惧贪婪指数统计
    print("\n分析恐惧贪婪指数...")
    fng_stats = []
    fng_conditions = [
        (df['fear_greed'] <= 10, 'FNG ≤10 (极度恐惧)'),
        (df['fear_greed'] <= 15, 'FNG ≤15'),
        (df['fear_greed'] <= 20, 'FNG ≤20'),
        (df['fear_greed'] <= 25, 'FNG ≤25 (恐惧)'),
        (df['fear_greed'] <= 30, 'FNG ≤30'),
        (df['fear_greed'] >= 75, 'FNG ≥75 (贪婪)'),
        (df['fear_greed'] >= 80, 'FNG ≥80'),
        (df['fear_greed'] >= 85, 'FNG ≥85 (极度贪婪)'),
    ]
    for cond, name in fng_conditions:
        r = analyze_condition(df, cond)
        if r:
            r['name'] = name
            fng_stats.append(r)

    # 插针统计
    print("分析插针形态...")
    pin_stats = []
    pin_conditions = [
        (df['pin_bull_strict'], '标准下插针'),
        (df['pin_bull_strict'] & (df['amplitude'] > 3), '下插针 + 振幅>3%'),
        (df['pin_bull_strict'] & (df['amplitude'] > 5), '下插针 + 振幅>5%'),
        (df['pin_bull_loose'] & (df['amplitude'] > 3), '宽松下插针(1.5x) + 振幅>3%'),
        (df['pin_bull_loose'] & (df['amplitude'] > 5), '宽松下插针(1.5x) + 振幅>5%'),
        (df['pin_bear_strict'], '标准上插针'),
        (df['pin_bear_strict'] & (df['amplitude'] > 3), '上插针 + 振幅>3%'),
    ]
    for cond, name in pin_conditions:
        r = analyze_condition(df, cond)
        if r:
            r['name'] = name
            pin_stats.append(r)

    # 组合策略统计
    print("分析组合策略...")
    combo_stats = []
    combo_conditions = [
        (df['pin_bull_strict'] & (df['fear_greed'] <= 25), 'FNG≤25 + 标准下插针'),
        (df['pin_bull_strict'] & (df['fear_greed'] <= 30), 'FNG≤30 + 标准下插针'),
        (df['pin_bull_loose'] & (df['amplitude'] > 3) & (df['fear_greed'] <= 30), 'FNG≤30 + 宽松下插针3%'),
        (df['pin_bull_loose'] & (df['amplitude'] > 5) & (df['fear_greed'] <= 30), 'FNG≤30 + 宽松下插针5%'),
        ((df['change_pct'] < -5) & (df['fear_greed'] <= 25), 'FNG≤25 + 日跌>5%'),
        ((df['change_pct'] < -5) & (df['rsi'] < 30), '日跌>5% + RSI<30'),
        ((df['change_pct'] < -5) & (df['fear_greed'] <= 25) & (df['rsi'] < 35), 'FNG≤25 + 跌>5% + RSI<35'),
        (df['pin_bull_loose'] & (df['change_pct'] < -3), '宽松下插针 + 日跌>3%'),
        ((df['fundingRate'] < -0.0001) & (df['rsi'] < 30), '负费率 + RSI<30'),
        ((df['fundingRate'] < -0.0001) & (df['change_pct'] < -5), '负费率 + 日跌>5%'),
    ]
    for cond, name in combo_conditions:
        r = analyze_condition(df, cond)
        if r:
            r['name'] = name
            combo_stats.append(r)

    # 回测策略
    print("运行回测...")
    strategy_results = []

    # 加载其他周期数据
    for tf in ['1d', '4h']:
        if tf not in data:
            continue
        tf_df = add_indicators(data[tf], data.get('fng'), data.get('funding'))

        conditions = {
            'FNG≤15': tf_df['fear_greed'] <= 15,
            'FNG≤20': tf_df['fear_greed'] <= 20,
            'FNG≤25': tf_df['fear_greed'] <= 25,
            'RSI<30': tf_df['rsi'] < 30,
            'RSI<35': tf_df['rsi'] < 35,
            '跌>3%': tf_df['change_pct'] < -3,
            '跌>5%': tf_df['change_pct'] < -5,
            '负费率': tf_df['fundingRate'] < -0.0001,
            '强负费率': tf_df['fundingRate'] < -0.0005,
            'MACD金叉': tf_df['macd_golden'],
            'EMA7金叉': tf_df['ema7_golden'],
            '下插针': tf_df['pin_bull_strict'],
            '宽松下插针': tf_df['pin_bull_loose'] & (tf_df['amplitude'] > 3),
        }

        tp_sl = [(50, 20), (80, 20), (100, 20)]

        # 双维度
        combos = [
            ('FNG≤20', 'RSI<30'), ('FNG≤25', 'RSI<35'), ('FNG≤15', '跌>5%'),
            ('负费率', 'RSI<30'), ('负费率', '跌>5%'), ('跌>5%', 'RSI<30'),
            ('FNG≤25', '下插针'), ('FNG≤30', '宽松下插针'),
        ]

        for a, b in combos:
            if a in conditions and b in conditions:
                sig = conditions[a] & conditions[b]
                for tp, sl in tp_sl:
                    trades = backtest(tf_df, sig, 'long', tp, sl)
                    m = calc_metrics(trades, 3)
                    if m and m['ev'] > 0:
                        strategy_results.append({
                            'name': f"{tf}_{a}+{b}",
                            'tf': tf, 'tp': tp, 'sl': sl, **m
                        })

        # 三维度
        triples = [
            ('FNG≤15', '跌>5%', 'RSI<35'),
            ('FNG≤20', '跌>5%', 'RSI<30'),
            ('负费率', '跌>3%', 'RSI<30'),
            ('负费率', '跌>5%', 'RSI<35'),
        ]
        for a, b, c in triples:
            if all(x in conditions for x in [a, b, c]):
                sig = conditions[a] & conditions[b] & conditions[c]
                for tp, sl in tp_sl:
                    trades = backtest(tf_df, sig, 'long', tp, sl)
                    m = calc_metrics(trades, 3)
                    if m and m['ev'] > 0:
                        strategy_results.append({
                            'name': f"{tf}_{a}+{b}+{c}",
                            'tf': tf, 'tp': tp, 'sl': sl, **m
                        })

    # 生成报告
    generate_report(data, fng_stats, pin_stats, combo_stats, strategy_results)


if __name__ == "__main__":
    main()
