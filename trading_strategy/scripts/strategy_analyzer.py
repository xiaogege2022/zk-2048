#!/usr/bin/env python3
"""
BTC/USDT 策略分析模块
Phase 2-4: 计算技术指标、遍历策略组合、回测验证
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import os
import warnings
warnings.filterwarnings('ignore')

DATA_DIR = "/home/user/zk-2048/trading_strategy/data"


class TechnicalIndicators:
    """技术指标计算器"""

    @staticmethod
    def ema(series, period):
        """指数移动平均"""
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series, period):
        """简单移动平均"""
        return series.rolling(window=period).mean()

    @staticmethod
    def rsi(series, period=14):
        """相对强弱指标"""
        delta = series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def macd(series, fast=12, slow=26, signal=9):
        """MACD指标"""
        ema_fast = series.ewm(span=fast, adjust=False).mean()
        ema_slow = series.ewm(span=slow, adjust=False).mean()
        dif = ema_fast - ema_slow
        dea = dif.ewm(span=signal, adjust=False).mean()
        macd_hist = (dif - dea) * 2
        return dif, dea, macd_hist

    @staticmethod
    def bollinger_bands(series, period=20, std_dev=2):
        """布林带"""
        middle = series.rolling(window=period).mean()
        std = series.rolling(window=period).std()
        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)
        return upper, middle, lower

    @staticmethod
    def add_all_indicators(df):
        """添加所有技术指标到DataFrame"""
        close = df['close']
        high = df['high']
        low = df['low']
        volume = df['volume']

        # EMA
        for period in [7, 25, 50, 99, 200]:
            df[f'ema_{period}'] = TechnicalIndicators.ema(close, period)

        # RSI
        df['rsi_14'] = TechnicalIndicators.rsi(close, 14)

        # MACD
        df['macd_dif'], df['macd_dea'], df['macd_hist'] = TechnicalIndicators.macd(close)

        # 布林带
        df['bb_upper'], df['bb_middle'], df['bb_lower'] = TechnicalIndicators.bollinger_bands(close)

        # 成交量均线
        df['vol_ma20'] = TechnicalIndicators.sma(volume, 20)
        df['vol_ratio'] = volume / df['vol_ma20']

        # K线形态
        df['body'] = abs(close - df['open'])
        df['upper_shadow'] = high - np.maximum(close, df['open'])
        df['lower_shadow'] = np.minimum(close, df['open']) - low
        df['amplitude'] = (high - low) / df['open'] * 100  # 振幅%

        # 涨跌幅
        df['change_pct'] = close.pct_change() * 100

        # EMA交叉信号
        df['ema7_cross_ema25'] = np.where(
            (df['ema_7'] > df['ema_25']) & (df['ema_7'].shift(1) <= df['ema_25'].shift(1)), 1,
            np.where((df['ema_7'] < df['ema_25']) & (df['ema_7'].shift(1) >= df['ema_25'].shift(1)), -1, 0)
        )

        # MACD交叉信号
        df['macd_cross'] = np.where(
            (df['macd_dif'] > df['macd_dea']) & (df['macd_dif'].shift(1) <= df['macd_dea'].shift(1)), 1,
            np.where((df['macd_dif'] < df['macd_dea']) & (df['macd_dif'].shift(1) >= df['macd_dea'].shift(1)), -1, 0)
        )

        # 插针检测
        df['pin_bar_bullish'] = (df['lower_shadow'] > df['body'] * 2) & (df['upper_shadow'] < df['body'] * 0.5) & (df['amplitude'] > 3)
        df['pin_bar_bearish'] = (df['upper_shadow'] > df['body'] * 2) & (df['lower_shadow'] < df['body'] * 0.5) & (df['amplitude'] > 3)

        return df


class StrategyAnalyzer:
    """策略分析器"""

    def __init__(self):
        self.kline_data = {}
        self.funding_data = None
        self.fng_data = None
        self.results = []

    def load_data(self):
        """加载所有数据"""
        print("加载数据...")

        # 加载K线数据
        for interval in ['1d', '4h', '1h']:
            filepath = f"{DATA_DIR}/BTCUSDT_{interval}.csv"
            if os.path.exists(filepath):
                df = pd.read_csv(filepath, parse_dates=['open_time', 'close_time'])
                df = TechnicalIndicators.add_all_indicators(df)
                self.kline_data[interval] = df
                print(f"  加载 {interval}: {len(df)} 条记录")

        # 加载资金费率
        filepath = f"{DATA_DIR}/funding_rate.csv"
        if os.path.exists(filepath):
            self.funding_data = pd.read_csv(filepath, parse_dates=['fundingTime'])
            print(f"  加载资金费率: {len(self.funding_data)} 条记录")

        # 加载恐惧贪婪指数
        filepath = f"{DATA_DIR}/fear_greed_index.csv"
        if os.path.exists(filepath):
            self.fng_data = pd.read_csv(filepath, parse_dates=['timestamp'])
            print(f"  加载恐惧贪婪指数: {len(self.fng_data)} 条记录")

        return len(self.kline_data) > 0

    def merge_external_data(self, df, timeframe='1d'):
        """合并外部数据(恐惧贪婪指数、资金费率)"""
        df = df.copy()

        # 合并恐惧贪婪指数
        if self.fng_data is not None:
            fng = self.fng_data[['timestamp', 'value']].rename(columns={'value': 'fear_greed'})
            fng['date'] = fng['timestamp'].dt.date
            df['date'] = df['open_time'].dt.date
            df = df.merge(fng[['date', 'fear_greed']], on='date', how='left')
            df['fear_greed'] = df['fear_greed'].fillna(method='ffill')

        # 合并资金费率
        if self.funding_data is not None:
            funding = self.funding_data[['fundingTime', 'fundingRate']].copy()
            funding['date'] = funding['fundingTime'].dt.date
            daily_funding = funding.groupby('date')['fundingRate'].mean().reset_index()
            df = df.merge(daily_funding, on='date', how='left')
            df['fundingRate'] = df['fundingRate'].fillna(0)

        return df

    def define_conditions(self):
        """定义所有策略条件"""
        conditions = {
            # 2.3 恐惧贪婪指数条件
            'fng_extreme_fear': lambda df: df['fear_greed'] <= 15,
            'fng_fear': lambda df: df['fear_greed'] <= 25,
            'fng_moderate_fear': lambda df: df['fear_greed'] <= 35,
            'fng_greed': lambda df: df['fear_greed'] >= 75,
            'fng_extreme_greed': lambda df: df['fear_greed'] >= 85,

            # 2.4 插针条件
            'pin_bullish_3pct': lambda df: df['pin_bar_bullish'] & (df['amplitude'] > 3),
            'pin_bullish_5pct': lambda df: df['pin_bar_bullish'] & (df['amplitude'] > 5),
            'pin_bullish_8pct': lambda df: df['pin_bar_bullish'] & (df['amplitude'] > 8),
            'pin_bearish_3pct': lambda df: df['pin_bar_bearish'] & (df['amplitude'] > 3),
            'pin_bearish_5pct': lambda df: df['pin_bar_bearish'] & (df['amplitude'] > 5),

            # 2.5 成交量条件
            'vol_surge_2x': lambda df: df['vol_ratio'] > 2,
            'vol_surge_3x': lambda df: df['vol_ratio'] > 3,
            'vol_low': lambda df: df['vol_ratio'] < 0.5,

            # 2.6 涨跌幅条件
            'drop_5pct': lambda df: df['change_pct'] < -5,
            'drop_10pct': lambda df: df['change_pct'] < -10,
            'drop_15pct': lambda df: df['change_pct'] < -15,
            'rise_5pct': lambda df: df['change_pct'] > 5,
            'rise_10pct': lambda df: df['change_pct'] > 10,

            # 2.7 资金费率条件
            'funding_negative': lambda df: df['fundingRate'] < -0.0001,
            'funding_very_negative': lambda df: df['fundingRate'] < -0.001,
            'funding_positive': lambda df: df['fundingRate'] > 0.001,
            'funding_very_positive': lambda df: df['fundingRate'] > 0.003,

            # 2.9 技术指标条件
            'ema7_cross_up': lambda df: df['ema7_cross_ema25'] == 1,
            'ema7_cross_down': lambda df: df['ema7_cross_ema25'] == -1,
            'macd_golden': lambda df: df['macd_cross'] == 1,
            'macd_death': lambda df: df['macd_cross'] == -1,
            'rsi_oversold': lambda df: df['rsi_14'] < 30,
            'rsi_very_oversold': lambda df: df['rsi_14'] < 20,
            'rsi_overbought': lambda df: df['rsi_14'] > 70,
            'rsi_very_overbought': lambda df: df['rsi_14'] > 80,
            'price_below_bb_lower': lambda df: df['close'] < df['bb_lower'],
            'price_above_bb_upper': lambda df: df['close'] > df['bb_upper'],
        }
        return conditions

    def backtest_strategy(self, df, entry_signals, direction='long',
                          tp_pct=50, sl_pct=20, leverage=10, max_hold=30):
        """
        回测单个策略
        tp_pct, sl_pct: 保证金盈亏百分比
        """
        trades = []
        position = None

        # 转换为现货价格变动
        tp_spot = tp_pct / leverage / 100  # 止盈现货涨幅
        sl_spot = sl_pct / leverage / 100  # 止损现货跌幅

        for i in range(len(df) - max_hold - 1):
            if position is None and entry_signals.iloc[i]:
                # 开仓
                entry_price = df['open'].iloc[i + 1]  # 下一根K线开盘价入场
                position = {
                    'entry_idx': i + 1,
                    'entry_price': entry_price,
                    'entry_time': df['open_time'].iloc[i + 1],
                    'direction': direction,
                    'highest': entry_price,
                    'lowest': entry_price
                }

            elif position is not None:
                idx = i + 1
                high = df['high'].iloc[idx]
                low = df['low'].iloc[idx]
                close = df['close'].iloc[idx]
                entry_price = position['entry_price']

                # 更新最高最低价
                position['highest'] = max(position['highest'], high)
                position['lowest'] = min(position['lowest'], low)

                # 计算止盈止损价格
                if direction == 'long':
                    tp_price = entry_price * (1 + tp_spot)
                    sl_price = entry_price * (1 - sl_spot)
                    hit_tp = high >= tp_price
                    hit_sl = low <= sl_price
                else:  # short
                    tp_price = entry_price * (1 - tp_spot)
                    sl_price = entry_price * (1 + sl_spot)
                    hit_tp = low <= tp_price
                    hit_sl = high >= sl_price

                # 检查是否平仓
                exit_reason = None
                exit_price = None

                if hit_sl and hit_tp:
                    # 同一K线同时触及，止损优先
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
                    # 计算收益
                    if direction == 'long':
                        spot_return = (exit_price - entry_price) / entry_price
                    else:
                        spot_return = (entry_price - exit_price) / entry_price

                    margin_return = spot_return * leverage  # 保证金收益率

                    trades.append({
                        'entry_time': position['entry_time'],
                        'entry_price': entry_price,
                        'exit_time': df['open_time'].iloc[idx],
                        'exit_price': exit_price,
                        'exit_reason': exit_reason,
                        'spot_return': spot_return * 100,
                        'margin_return': margin_return * 100,
                        'hold_bars': idx - position['entry_idx']
                    })
                    position = None

        return pd.DataFrame(trades) if trades else None

    def calculate_strategy_metrics(self, trades_df):
        """计算策略指标"""
        if trades_df is None or len(trades_df) == 0:
            return None

        n_trades = len(trades_df)
        wins = trades_df[trades_df['margin_return'] > 0]
        losses = trades_df[trades_df['margin_return'] <= 0]

        win_rate = len(wins) / n_trades * 100 if n_trades > 0 else 0
        avg_win = wins['margin_return'].mean() if len(wins) > 0 else 0
        avg_loss = abs(losses['margin_return'].mean()) if len(losses) > 0 else 0

        # EV = 胜率×平均盈利 - (1-胜率)×平均亏损
        ev = (win_rate / 100 * avg_win) - ((1 - win_rate / 100) * avg_loss)

        # 盈亏比
        profit_loss_ratio = avg_win / avg_loss if avg_loss > 0 else float('inf')

        return {
            'n_trades': n_trades,
            'win_rate': win_rate,
            'avg_win': avg_win,
            'avg_loss': avg_loss,
            'ev': ev,
            'profit_loss_ratio': profit_loss_ratio,
            'total_return': trades_df['margin_return'].sum()
        }

    def run_single_condition_test(self, condition_name, condition_func, timeframe='1d',
                                  direction='long', tp_pct=50, sl_pct=20):
        """测试单个条件"""
        if timeframe not in self.kline_data:
            return None

        df = self.kline_data[timeframe].copy()
        df = self.merge_external_data(df, timeframe)

        try:
            signals = condition_func(df)
            trades = self.backtest_strategy(df, signals, direction, tp_pct, sl_pct)
            metrics = self.calculate_strategy_metrics(trades)

            if metrics and metrics['n_trades'] >= 10:  # 至少10次交易
                return {
                    'strategy': condition_name,
                    'timeframe': timeframe,
                    'direction': direction,
                    'tp_pct': tp_pct,
                    'sl_pct': sl_pct,
                    **metrics
                }
        except Exception as e:
            print(f"  测试 {condition_name} 失败: {e}")

        return None

    def run_combo_test(self, conditions_list, condition_funcs, timeframe='1d',
                       direction='long', tp_pct=50, sl_pct=20):
        """测试组合条件"""
        if timeframe not in self.kline_data:
            return None

        df = self.kline_data[timeframe].copy()
        df = self.merge_external_data(df, timeframe)

        try:
            # 组合所有条件 (AND)
            combined_signal = pd.Series([True] * len(df), index=df.index)
            for cond_name in conditions_list:
                combined_signal &= condition_funcs[cond_name](df)

            trades = self.backtest_strategy(df, combined_signal, direction, tp_pct, sl_pct)
            metrics = self.calculate_strategy_metrics(trades)

            if metrics and metrics['n_trades'] >= 5:  # 组合条件至少5次交易
                return {
                    'strategy': ' + '.join(conditions_list),
                    'timeframe': timeframe,
                    'direction': direction,
                    'tp_pct': tp_pct,
                    'sl_pct': sl_pct,
                    **metrics
                }
        except Exception as e:
            pass

        return None

    def run_full_analysis(self):
        """运行完整分析"""
        if not self.load_data():
            print("数据加载失败!")
            return []

        conditions = self.define_conditions()
        results = []
        total_tests = 0

        print("\n开始策略遍历分析...")

        # 1. 单维度测试
        print("\n=== 单维度策略测试 ===")
        timeframes = ['1d', '4h', '1h']
        tp_sl_combos = [(50, 20), (100, 20), (50, 10), (100, 30)]

        for tf in timeframes:
            for cond_name, cond_func in conditions.items():
                for tp, sl in tp_sl_combos:
                    for direction in ['long', 'short']:
                        result = self.run_single_condition_test(
                            cond_name, cond_func, tf, direction, tp, sl
                        )
                        if result:
                            results.append(result)
                        total_tests += 1

        print(f"  单维度测试完成: {total_tests} 次, 有效策略: {len(results)} 个")

        # 2. 双维度组合测试
        print("\n=== 双维度策略测试 ===")
        cond_names = list(conditions.keys())
        combo_count = 0

        # 重点组合: 恐惧贪婪 + 技术指标
        fng_conds = [c for c in cond_names if c.startswith('fng_')]
        tech_conds = [c for c in cond_names if c.startswith(('rsi_', 'ema7_', 'macd_', 'pin_'))]

        for fng in fng_conds:
            for tech in tech_conds:
                for tf in timeframes:
                    for tp, sl in tp_sl_combos[:2]:  # 减少组合数
                        direction = 'long' if 'fear' in fng or 'oversold' in tech or 'bullish' in tech else 'short'
                        result = self.run_combo_test([fng, tech], conditions, tf, direction, tp, sl)
                        if result:
                            results.append(result)
                        combo_count += 1

        print(f"  双维度测试完成: {combo_count} 次")

        # 3. 三维度组合测试
        print("\n=== 三维度策略测试 ===")
        vol_conds = [c for c in cond_names if c.startswith('vol_')]
        drop_conds = [c for c in cond_names if c.startswith('drop_')]

        triple_count = 0
        for fng in fng_conds[:3]:  # 限制数量
            for drop in drop_conds:
                for tech in tech_conds[:5]:
                    for tf in ['1d', '4h']:
                        result = self.run_combo_test([fng, drop, tech], conditions, tf, 'long', 50, 20)
                        if result:
                            results.append(result)
                        triple_count += 1

        print(f"  三维度测试完成: {triple_count} 次")

        total_tests += combo_count + triple_count
        print(f"\n总计测试: {total_tests} 个策略组合")
        print(f"有效策略: {len(results)} 个")

        self.results = results
        return results


def main():
    """主函数"""
    analyzer = StrategyAnalyzer()
    results = analyzer.run_full_analysis()

    if results:
        # 转换为DataFrame并排序
        df = pd.DataFrame(results)
        df = df.sort_values('ev', ascending=False)

        # 保存结果
        output_file = f"{DATA_DIR}/strategy_results.csv"
        df.to_csv(output_file, index=False)
        print(f"\n结果已保存: {output_file}")

        # 显示Top 20
        print("\n" + "=" * 80)
        print("TOP 20 最优EV策略")
        print("=" * 80)

        top20 = df.head(20)
        for i, row in top20.iterrows():
            print(f"\n【排名 {top20.index.get_loc(i) + 1}】")
            print(f"  策略: {row['strategy']}")
            print(f"  周期: {row['timeframe']} | 方向: {row['direction']}")
            print(f"  止盈/止损: {row['tp_pct']}% / {row['sl_pct']}%")
            print(f"  胜率: {row['win_rate']:.1f}% | 交易次数: {row['n_trades']}")
            print(f"  平均盈利: {row['avg_win']:.1f}% | 平均亏损: {row['avg_loss']:.1f}%")
            print(f"  EV: {row['ev']:.2f}% | 盈亏比: {row['profit_loss_ratio']:.2f}")

        return df

    return None


if __name__ == "__main__":
    main()
