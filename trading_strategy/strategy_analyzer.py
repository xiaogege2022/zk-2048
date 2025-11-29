#!/usr/bin/env python3
"""
BTC/USDT Comprehensive Strategy Analyzer and Backtester
Analyzes all 9 dimensions (2.1-2.9) and generates optimal trading strategies
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from itertools import combinations
import warnings
warnings.filterwarnings('ignore')

class IndicatorCalculator:
    """Calculate all technical indicators"""

    @staticmethod
    def ema(series, period):
        return series.ewm(span=period, adjust=False).mean()

    @staticmethod
    def sma(series, period):
        return series.rolling(window=period).mean()

    @staticmethod
    def macd(close, fast=12, slow=26, signal=9):
        fast_ema = IndicatorCalculator.ema(close, fast)
        slow_ema = IndicatorCalculator.ema(close, slow)
        macd_line = fast_ema - slow_ema
        signal_line = IndicatorCalculator.ema(macd_line, signal)
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram

    @staticmethod
    def rsi(close, period=14):
        delta = close.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        return 100 - (100 / (1 + rs))

    @staticmethod
    def atr(high, low, close, period=14):
        tr1 = high - low
        tr2 = abs(high - close.shift())
        tr3 = abs(low - close.shift())
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        return tr.rolling(window=period).mean()

    @staticmethod
    def bollinger_bands(close, period=20, std_dev=2):
        middle = close.rolling(window=period).mean()
        std = close.rolling(window=period).std()
        upper = middle + (std_dev * std)
        lower = middle - (std_dev * std)
        return upper, middle, lower

    @staticmethod
    def calculate_volatility(close, period=20):
        returns = close.pct_change()
        return returns.rolling(window=period).std() * np.sqrt(252)


class PatternDetector:
    """Detect K-line patterns and market structure"""

    @staticmethod
    def detect_pin_bar(high, low, open_price, close, threshold=0.5):
        """Detect pin bar / wick patterns"""
        body = abs(close - open_price)
        total_range = high - low
        upper_wick = high - np.maximum(open_price, close)
        lower_wick = np.minimum(open_price, close) - low

        # Bullish pin bar (hammer)
        bullish_pin = (lower_wick > body * 2) & (lower_wick > upper_wick * 2)
        # Bearish pin bar (shooting star)
        bearish_pin = (upper_wick > body * 2) & (upper_wick > lower_wick * 2)

        return bullish_pin, bearish_pin

    @staticmethod
    def detect_large_wick(high, low, close, threshold_pct=3):
        """Detect large wicks indicating potential reversal"""
        total_range_pct = (high - low) / close * 100
        return total_range_pct > threshold_pct

    @staticmethod
    def detect_trend(close, periods=[7, 25, 99]):
        """Detect trend using multiple EMAs"""
        emas = {p: IndicatorCalculator.ema(close, p) for p in periods}

        # Strong uptrend: EMA7 > EMA25 > EMA99
        uptrend = (emas[7] > emas[25]) & (emas[25] > emas[99])
        # Strong downtrend: EMA7 < EMA25 < EMA99
        downtrend = (emas[7] < emas[25]) & (emas[25] < emas[99])
        # Consolidation
        consolidation = ~uptrend & ~downtrend

        return uptrend, downtrend, consolidation, emas

    @staticmethod
    def detect_ema_crossover(close, fast=7, slow=25):
        """Detect EMA crossovers"""
        ema_fast = IndicatorCalculator.ema(close, fast)
        ema_slow = IndicatorCalculator.ema(close, slow)

        # Golden cross (bullish)
        golden_cross = (ema_fast > ema_slow) & (ema_fast.shift(1) <= ema_slow.shift(1))
        # Death cross (bearish)
        death_cross = (ema_fast < ema_slow) & (ema_fast.shift(1) >= ema_slow.shift(1))

        return golden_cross, death_cross, ema_fast, ema_slow


class StrategyEngine:
    """Main strategy analysis engine"""

    def __init__(self, data_dir='data'):
        self.data_dir = data_dir
        self.df = None
        self.fgi = None
        self.funding = None
        self.oi = None
        self.signals = {}
        self.strategies = []

    def load_data(self):
        """Load all data files"""
        print("Loading data...")

        # Load price data
        self.df = pd.read_csv(f'{self.data_dir}/BTCUSDT_1d.csv')
        self.df['open_time'] = pd.to_datetime(self.df['open_time'])
        self.df.set_index('open_time', inplace=True)

        # Load Fear & Greed Index
        self.fgi = pd.read_csv(f'{self.data_dir}/fear_greed_index.csv')
        self.fgi['timestamp'] = pd.to_datetime(self.fgi['timestamp'])
        self.fgi.set_index('timestamp', inplace=True)

        # Load Funding Rate
        self.funding = pd.read_csv(f'{self.data_dir}/BTCUSDT_funding_rate.csv')
        self.funding['funding_time'] = pd.to_datetime(self.funding['funding_time'])
        # Resample to daily
        self.funding = self.funding.set_index('funding_time').resample('D').mean()

        # Load Open Interest
        self.oi = pd.read_csv(f'{self.data_dir}/BTCUSDT_oi.csv')
        self.oi['timestamp'] = pd.to_datetime(self.oi['timestamp'])
        self.oi.set_index('timestamp', inplace=True)

        # Merge all data
        self.df = self.df.join(self.fgi[['value']], how='left')
        self.df.rename(columns={'value': 'fear_greed'}, inplace=True)
        self.df = self.df.join(self.funding, how='left')
        self.df = self.df.join(self.oi, how='left')

        # Forward fill missing values
        self.df = self.df.ffill().bfill()

        print(f"Loaded {len(self.df)} records from {self.df.index.min()} to {self.df.index.max()}")

    def calculate_indicators(self):
        """Calculate all technical indicators"""
        print("Calculating indicators...")

        # EMAs
        for period in [7, 9, 12, 21, 25, 50, 99, 200]:
            self.df[f'ema_{period}'] = IndicatorCalculator.ema(self.df['close'], period)

        # SMAs
        for period in [20, 50, 100, 200]:
            self.df[f'sma_{period}'] = IndicatorCalculator.sma(self.df['close'], period)

        # MACD
        self.df['macd'], self.df['macd_signal'], self.df['macd_hist'] = \
            IndicatorCalculator.macd(self.df['close'])

        # RSI
        self.df['rsi'] = IndicatorCalculator.rsi(self.df['close'])

        # ATR
        self.df['atr'] = IndicatorCalculator.atr(self.df['high'], self.df['low'], self.df['close'])
        self.df['atr_pct'] = self.df['atr'] / self.df['close'] * 100

        # Bollinger Bands
        self.df['bb_upper'], self.df['bb_middle'], self.df['bb_lower'] = \
            IndicatorCalculator.bollinger_bands(self.df['close'])

        # Volatility
        self.df['volatility'] = IndicatorCalculator.calculate_volatility(self.df['close'])

        # Price changes
        for period in [1, 3, 5, 7, 14, 30]:
            self.df[f'change_{period}d'] = self.df['close'].pct_change(period) * 100

        # Volume changes
        self.df['volume_sma_20'] = self.df['volume'].rolling(20).mean()
        self.df['volume_ratio'] = self.df['volume'] / self.df['volume_sma_20']

        # Wick analysis
        self.df['upper_wick'] = self.df['high'] - np.maximum(self.df['open'], self.df['close'])
        self.df['lower_wick'] = np.minimum(self.df['open'], self.df['close']) - self.df['low']
        self.df['body'] = abs(self.df['close'] - self.df['open'])
        self.df['total_range'] = self.df['high'] - self.df['low']
        self.df['wick_ratio'] = (self.df['upper_wick'] + self.df['lower_wick']) / self.df['body'].replace(0, 0.01)

        # Pin bar detection
        self.df['bullish_pin'], self.df['bearish_pin'] = PatternDetector.detect_pin_bar(
            self.df['high'], self.df['low'], self.df['open'], self.df['close'])

        # Large wick detection
        for thresh in [3, 5, 7, 10]:
            self.df[f'large_wick_{thresh}pct'] = PatternDetector.detect_large_wick(
                self.df['high'], self.df['low'], self.df['close'], thresh)

        # Trend detection
        self.df['uptrend'], self.df['downtrend'], self.df['consolidation'], _ = \
            PatternDetector.detect_trend(self.df['close'])

        # EMA crossovers
        for fast, slow in [(7, 25), (9, 21), (12, 26), (50, 200)]:
            col_prefix = f'ema_{fast}_{slow}'
            self.df[f'{col_prefix}_golden'], self.df[f'{col_prefix}_death'], _, _ = \
                PatternDetector.detect_ema_crossover(self.df['close'], fast, slow)

        # MACD crossovers
        self.df['macd_bullish'] = (self.df['macd'] > self.df['macd_signal']) & \
                                   (self.df['macd'].shift(1) <= self.df['macd_signal'].shift(1))
        self.df['macd_bearish'] = (self.df['macd'] < self.df['macd_signal']) & \
                                   (self.df['macd'].shift(1) >= self.df['macd_signal'].shift(1))

        # Fear & Greed zones
        self.df['extreme_fear'] = self.df['fear_greed'] <= 20
        self.df['fear'] = (self.df['fear_greed'] > 20) & (self.df['fear_greed'] <= 40)
        self.df['neutral'] = (self.df['fear_greed'] > 40) & (self.df['fear_greed'] <= 60)
        self.df['greed'] = (self.df['fear_greed'] > 60) & (self.df['fear_greed'] <= 80)
        self.df['extreme_greed'] = self.df['fear_greed'] > 80

        # Funding rate zones
        self.df['negative_funding'] = self.df['funding_rate'] < -0.001
        self.df['very_negative_funding'] = self.df['funding_rate'] < -0.005
        self.df['positive_funding'] = self.df['funding_rate'] > 0.001
        self.df['very_positive_funding'] = self.df['funding_rate'] > 0.005

        # OI changes
        self.df['oi_change'] = self.df['open_interest'].pct_change() * 100
        self.df['oi_drop'] = self.df['oi_change'] < -5  # Large liquidations
        self.df['oi_spike'] = self.df['oi_change'] > 10  # Large position buildup

        # Consecutive days analysis
        self.df['consecutive_up'] = 0
        self.df['consecutive_down'] = 0
        up_count = 0
        down_count = 0
        for i in range(1, len(self.df)):
            if self.df['close'].iloc[i] > self.df['close'].iloc[i-1]:
                up_count += 1
                down_count = 0
            elif self.df['close'].iloc[i] < self.df['close'].iloc[i-1]:
                down_count += 1
                up_count = 0
            else:
                up_count = 0
                down_count = 0
            self.df.iloc[i, self.df.columns.get_loc('consecutive_up')] = up_count
            self.df.iloc[i, self.df.columns.get_loc('consecutive_down')] = down_count

        print(f"Calculated {len([c for c in self.df.columns if c not in ['open', 'high', 'low', 'close', 'volume']])} indicators")

    def generate_signals(self):
        """Generate trading signals for all strategies"""
        print("Generating signals...")

        # ===== 2.1 K-line Pattern Signals =====
        # Weekly consolidation breakout (simulated with 7-day range)
        self.df['range_7d'] = self.df['high'].rolling(7).max() - self.df['low'].rolling(7).min()
        self.df['range_7d_pct'] = self.df['range_7d'] / self.df['close'] * 100
        self.df['tight_range'] = self.df['range_7d_pct'] < 10  # Less than 10% range = consolidation
        self.df['breakout_up'] = (self.df['close'] > self.df['high'].rolling(7).max().shift(1)) & self.df['tight_range'].shift(1)
        self.df['breakout_down'] = (self.df['close'] < self.df['low'].rolling(7).min().shift(1)) & self.df['tight_range'].shift(1)

        # ===== 2.3 Fear & Greed Signals =====
        # Extreme fear = buy signal
        self.df['fgi_buy'] = self.df['fear_greed'] <= 15
        self.df['fgi_strong_buy'] = self.df['fear_greed'] <= 10
        # Extreme greed = sell signal
        self.df['fgi_sell'] = self.df['fear_greed'] >= 85
        self.df['fgi_strong_sell'] = self.df['fear_greed'] >= 90

        # ===== 2.4 Pin Bar / Wick Signals =====
        # Large lower wick after downtrend = potential bottom
        self.df['wick_bottom'] = (self.df['lower_wick'] > self.df['body'] * 2) & \
                                  (self.df['change_7d'] < -10)
        # Large upper wick after uptrend = potential top
        self.df['wick_top'] = (self.df['upper_wick'] > self.df['body'] * 2) & \
                              (self.df['change_7d'] > 10)

        # Flash crash detection (>5% intraday range with long lower wick)
        self.df['flash_crash'] = (self.df['total_range'] / self.df['close'] * 100 > 5) & \
                                 (self.df['lower_wick'] > self.df['upper_wick'] * 2)
        self.df['flash_pump'] = (self.df['total_range'] / self.df['close'] * 100 > 5) & \
                                (self.df['upper_wick'] > self.df['lower_wick'] * 2)

        # ===== 2.5 Volume Signals =====
        self.df['volume_surge'] = self.df['volume_ratio'] > 2  # 2x average volume
        self.df['volume_climax'] = self.df['volume_ratio'] > 3  # 3x average volume

        # ===== 2.6 Price Change Signals =====
        # Large drops = potential buy
        for drop in [10, 15, 20, 30]:
            self.df[f'drop_{drop}pct_7d'] = self.df['change_7d'] <= -drop
            self.df[f'drop_{drop}pct_3d'] = self.df['change_3d'] <= -drop
            self.df[f'drop_{drop}pct_1d'] = self.df['change_1d'] <= -drop

        # Large pumps = potential sell
        for pump in [10, 15, 20, 30]:
            self.df[f'pump_{pump}pct_7d'] = self.df['change_7d'] >= pump
            self.df[f'pump_{pump}pct_3d'] = self.df['change_3d'] >= pump
            self.df[f'pump_{pump}pct_1d'] = self.df['change_1d'] >= pump

        # ===== 2.7 Funding Rate Signals =====
        self.df['funding_buy'] = self.df['very_negative_funding']  # Shorts paying = oversold
        self.df['funding_sell'] = self.df['very_positive_funding']  # Longs paying = overbought

        # ===== 2.8 OI Signals =====
        self.df['oi_liquidation'] = self.df['oi_drop'] & (self.df['change_1d'] < -5)  # Forced liquidation
        self.df['oi_fomo'] = self.df['oi_spike'] & (self.df['change_1d'] > 5)  # FOMO entry

        # ===== 2.9 Technical Indicator Signals =====
        # EMA crossover signals already calculated above
        # MACD signals already calculated above

        # RSI signals
        self.df['rsi_oversold'] = self.df['rsi'] < 30
        self.df['rsi_overbought'] = self.df['rsi'] > 70
        self.df['rsi_extreme_oversold'] = self.df['rsi'] < 20
        self.df['rsi_extreme_overbought'] = self.df['rsi'] > 80

        # Bollinger Band signals
        self.df['bb_oversold'] = self.df['close'] < self.df['bb_lower']
        self.df['bb_overbought'] = self.df['close'] > self.df['bb_upper']

        print("Signals generated successfully")

    def define_strategies(self):
        """Define all single and combination strategies"""
        print("Defining strategies...")

        self.strategies = []

        # ===== Single Strategies =====

        # Strategy 1: Extreme Fear Buy
        self.strategies.append({
            'name': 'Extreme_Fear_Buy',
            'type': 'single',
            'dimension': '2.3',
            'buy_condition': 'fgi_strong_buy',
            'sell_condition': 'fear_greed >= 50',
            'description': 'Buy when Fear & Greed <= 10, sell when >= 50'
        })

        # Strategy 2: EMA 7/25 Crossover
        self.strategies.append({
            'name': 'EMA_7_25_Cross',
            'type': 'single',
            'dimension': '2.9',
            'buy_condition': 'ema_7_25_golden',
            'sell_condition': 'ema_7_25_death',
            'description': 'Buy on EMA7 cross above EMA25, sell on cross below'
        })

        # Strategy 3: Flash Crash Bottom
        self.strategies.append({
            'name': 'Flash_Crash_Bottom',
            'type': 'single',
            'dimension': '2.4',
            'buy_condition': 'flash_crash',
            'sell_condition': 'change_7d >= 10',
            'description': 'Buy on flash crash (>5% range with long lower wick)'
        })

        # Strategy 4: Negative Funding Buy
        self.strategies.append({
            'name': 'Negative_Funding_Buy',
            'type': 'single',
            'dimension': '2.7',
            'buy_condition': 'very_negative_funding',
            'sell_condition': 'funding_rate >= 0',
            'description': 'Buy when funding very negative (shorts paying)'
        })

        # Strategy 5: Large Drop Buy
        self.strategies.append({
            'name': 'Large_Drop_20pct',
            'type': 'single',
            'dimension': '2.6',
            'buy_condition': 'drop_20pct_7d',
            'sell_condition': 'change_7d >= 15',
            'description': 'Buy on 20%+ weekly drop, sell on 15% recovery'
        })

        # Strategy 6: MACD Bullish Cross
        self.strategies.append({
            'name': 'MACD_Bullish_Cross',
            'type': 'single',
            'dimension': '2.9',
            'buy_condition': 'macd_bullish',
            'sell_condition': 'macd_bearish',
            'description': 'Buy on MACD bullish cross, sell on bearish cross'
        })

        # Strategy 7: RSI Oversold
        self.strategies.append({
            'name': 'RSI_Oversold',
            'type': 'single',
            'dimension': '2.9',
            'buy_condition': 'rsi_extreme_oversold',
            'sell_condition': 'rsi >= 50',
            'description': 'Buy when RSI < 20, sell when RSI >= 50'
        })

        # Strategy 8: Bollinger Band Oversold
        self.strategies.append({
            'name': 'BB_Oversold',
            'type': 'single',
            'dimension': '2.9',
            'buy_condition': 'bb_oversold',
            'sell_condition': 'close >= bb_middle',
            'description': 'Buy below lower BB, sell at middle BB'
        })

        # Strategy 9: Volume Climax Bottom
        self.strategies.append({
            'name': 'Volume_Climax_Bottom',
            'type': 'single',
            'dimension': '2.5',
            'buy_condition': 'volume_climax & (change_1d < -5)',
            'sell_condition': 'change_7d >= 10',
            'description': 'Buy on 3x volume with >5% drop (capitulation)'
        })

        # Strategy 10: OI Liquidation Buy
        self.strategies.append({
            'name': 'OI_Liquidation_Buy',
            'type': 'single',
            'dimension': '2.8',
            'buy_condition': 'oi_liquidation',
            'sell_condition': 'change_7d >= 10',
            'description': 'Buy when OI drops >5% with price drop (forced liquidation)'
        })

        # Strategy 11: Breakout After Consolidation
        self.strategies.append({
            'name': 'Breakout_Buy',
            'type': 'single',
            'dimension': '2.1',
            'buy_condition': 'breakout_up',
            'sell_condition': 'change_7d < -5',
            'description': 'Buy on breakout above 7-day range after consolidation'
        })

        # Strategy 12: EMA 50/200 Golden Cross
        self.strategies.append({
            'name': 'EMA_50_200_Cross',
            'type': 'single',
            'dimension': '2.9',
            'buy_condition': 'ema_50_200_golden',
            'sell_condition': 'ema_50_200_death',
            'description': 'Buy on EMA50 cross above EMA200 (major trend change)'
        })

        # Strategy 13: Bullish Pin Bar
        self.strategies.append({
            'name': 'Bullish_Pin_Bar',
            'type': 'single',
            'dimension': '2.4',
            'buy_condition': 'bullish_pin',
            'sell_condition': 'change_7d >= 10',
            'description': 'Buy on bullish pin bar (hammer)'
        })

        # Strategy 14: Large 1-Day Drop
        self.strategies.append({
            'name': 'Large_1D_Drop',
            'type': 'single',
            'dimension': '2.6',
            'buy_condition': 'drop_10pct_1d',
            'sell_condition': 'change_3d >= 5',
            'description': 'Buy on 10%+ single day drop'
        })

        # Strategy 15: Extreme Greed Short
        self.strategies.append({
            'name': 'Extreme_Greed_Short',
            'type': 'single',
            'dimension': '2.3',
            'buy_condition': 'fgi_strong_sell',  # This is short entry
            'sell_condition': 'fear_greed <= 50',
            'description': 'Short when Fear & Greed >= 90',
            'direction': 'short'
        })

        # ===== Combination Strategies =====

        # Combo 1: Fear + Large Drop (2.3 + 2.6)
        self.strategies.append({
            'name': 'Fear_Plus_Drop',
            'type': 'combo',
            'dimensions': ['2.3', '2.6'],
            'buy_condition': 'extreme_fear & drop_15pct_7d',
            'sell_condition': '(fear_greed >= 40) | (change_7d >= 20)',
            'description': 'Buy when extreme fear AND 15%+ weekly drop'
        })

        # Combo 2: Fear + Negative Funding (2.3 + 2.7)
        self.strategies.append({
            'name': 'Fear_Plus_NegFunding',
            'type': 'combo',
            'dimensions': ['2.3', '2.7'],
            'buy_condition': 'extreme_fear & negative_funding',
            'sell_condition': '(fear_greed >= 50) & (funding_rate >= 0)',
            'description': 'Buy when extreme fear AND negative funding'
        })

        # Combo 3: Flash Crash + Extreme Fear (2.4 + 2.3)
        self.strategies.append({
            'name': 'FlashCrash_Fear',
            'type': 'combo',
            'dimensions': ['2.3', '2.4'],
            'buy_condition': 'flash_crash & (fear_greed <= 25)',
            'sell_condition': '(fear_greed >= 50) | (change_14d >= 30)',
            'description': 'Buy on flash crash with fear'
        })

        # Combo 4: EMA Cross + Trend (2.9 + 2.1)
        self.strategies.append({
            'name': 'EMA_Cross_Trend',
            'type': 'combo',
            'dimensions': ['2.1', '2.9'],
            'buy_condition': 'ema_7_25_golden & uptrend',
            'sell_condition': 'ema_7_25_death | downtrend',
            'description': 'Buy on EMA cross when in uptrend'
        })

        # Combo 5: Volume + Drop + Fear (2.5 + 2.6 + 2.3)
        self.strategies.append({
            'name': 'Volume_Drop_Fear',
            'type': 'combo',
            'dimensions': ['2.3', '2.5', '2.6'],
            'buy_condition': 'volume_climax & drop_10pct_1d & (fear_greed <= 30)',
            'sell_condition': '(fear_greed >= 50) | (change_14d >= 30)',
            'description': 'Buy on volume climax with drop and fear'
        })

        # Combo 6: RSI + Fear + Drop (2.9 + 2.3 + 2.6)
        self.strategies.append({
            'name': 'RSI_Fear_Drop',
            'type': 'combo',
            'dimensions': ['2.3', '2.6', '2.9'],
            'buy_condition': 'rsi_extreme_oversold & extreme_fear & drop_15pct_7d',
            'sell_condition': '(rsi >= 60) | (fear_greed >= 60)',
            'description': 'Buy on oversold RSI with fear and drop'
        })

        # Combo 7: Funding + OI + Drop (2.7 + 2.8 + 2.6)
        self.strategies.append({
            'name': 'Funding_OI_Drop',
            'type': 'combo',
            'dimensions': ['2.6', '2.7', '2.8'],
            'buy_condition': 'very_negative_funding & oi_liquidation',
            'sell_condition': '(funding_rate >= 0.001) | (change_14d >= 25)',
            'description': 'Buy on negative funding with OI liquidation'
        })

        # Combo 8: All Technical Buy (2.9 multi)
        self.strategies.append({
            'name': 'All_Technical_Buy',
            'type': 'combo',
            'dimensions': ['2.9'],
            'buy_condition': 'rsi_oversold & bb_oversold & macd_bullish',
            'sell_condition': 'rsi_overbought | bb_overbought',
            'description': 'Buy when RSI, BB, and MACD all signal buy'
        })

        # Combo 9: Pin + Volume + Fear (2.4 + 2.5 + 2.3)
        self.strategies.append({
            'name': 'Pin_Volume_Fear',
            'type': 'combo',
            'dimensions': ['2.3', '2.4', '2.5'],
            'buy_condition': 'bullish_pin & volume_surge & (fear_greed <= 35)',
            'sell_condition': '(fear_greed >= 55) | (change_14d >= 25)',
            'description': 'Buy on pin bar with high volume and fear'
        })

        # Combo 10: Ultimate Bottom Signal (All Dimensions)
        self.strategies.append({
            'name': 'Ultimate_Bottom',
            'type': 'combo',
            'dimensions': ['2.3', '2.4', '2.5', '2.6', '2.7', '2.8', '2.9'],
            'buy_condition': 'extreme_fear & (flash_crash | bullish_pin) & volume_climax & drop_20pct_7d & negative_funding & oi_drop & rsi_extreme_oversold',
            'sell_condition': '(fear_greed >= 60) | (change_30d >= 50)',
            'description': 'Buy when ALL bottom indicators align'
        })

        # Short strategies
        # Combo 11: Greed + Pump Short (2.3 + 2.6)
        self.strategies.append({
            'name': 'Greed_Pump_Short',
            'type': 'combo',
            'dimensions': ['2.3', '2.6'],
            'buy_condition': 'extreme_greed & pump_20pct_7d',
            'sell_condition': '(fear_greed <= 50) | (change_7d <= -15)',
            'description': 'Short when extreme greed AND 20%+ weekly pump',
            'direction': 'short'
        })

        # Combo 12: Technical Top Short (2.9 multi)
        self.strategies.append({
            'name': 'Technical_Top_Short',
            'type': 'combo',
            'dimensions': ['2.9'],
            'buy_condition': 'rsi_extreme_overbought & bb_overbought & macd_bearish',
            'sell_condition': 'rsi_oversold | bb_oversold',
            'description': 'Short when RSI, BB, and MACD all signal sell',
            'direction': 'short'
        })

        # Additional combination strategies for comprehensive coverage
        # Combo 13-30: Generate systematic combinations
        single_conditions = [
            ('extreme_fear', '2.3', 'Fear'),
            ('very_negative_funding', '2.7', 'NegFund'),
            ('flash_crash', '2.4', 'Flash'),
            ('drop_15pct_7d', '2.6', 'Drop15'),
            ('volume_climax', '2.5', 'VolClx'),
            ('oi_liquidation', '2.8', 'OILiq'),
            ('rsi_extreme_oversold', '2.9', 'RSIos'),
            ('bullish_pin', '2.4', 'Pin'),
        ]

        # Generate 2-way combinations
        for i, (cond1, dim1, name1) in enumerate(single_conditions):
            for j, (cond2, dim2, name2) in enumerate(single_conditions):
                if i < j:
                    self.strategies.append({
                        'name': f'{name1}_{name2}_Combo',
                        'type': 'combo',
                        'dimensions': [dim1, dim2],
                        'buy_condition': f'{cond1} & {cond2}',
                        'sell_condition': '(fear_greed >= 55) | (change_14d >= 25)',
                        'description': f'Combination of {name1} and {name2}'
                    })

        print(f"Defined {len(self.strategies)} strategies")


class Backtester:
    """Backtesting engine with leverage and trailing stops"""

    def __init__(self, df, initial_capital=10000):
        self.df = df.copy()
        self.initial_capital = initial_capital

    def evaluate_condition(self, condition):
        """Safely evaluate a condition string"""
        try:
            # Handle complex conditions
            condition = condition.replace('&', ' & ').replace('|', ' | ')
            condition = condition.replace('  ', ' ')

            # Create local namespace with dataframe columns
            local_vars = {col: self.df[col] for col in self.df.columns}
            local_vars['np'] = np
            local_vars['pd'] = pd

            result = eval(condition, {"__builtins__": {}}, local_vars)
            return result
        except Exception as e:
            print(f"Error evaluating condition '{condition}': {e}")
            return pd.Series([False] * len(self.df), index=self.df.index)

    def backtest_strategy(self, strategy, leverage_range=(5, 50),
                         tp_range=(0.03, 0.50), sl_range=(0.02, 0.15),
                         trailing_stop=True, kelly_sizing=True,
                         start_date='2020-01-01', end_date='2025-11-20'):
        """
        Backtest a strategy with parameter optimization.
        Returns best parameters and performance metrics.
        """

        # Filter date range
        mask = (self.df.index >= start_date) & (self.df.index <= end_date)
        df_test = self.df[mask].copy()

        if len(df_test) < 30:
            return None

        direction = strategy.get('direction', 'long')

        # Get buy signals
        buy_signals = self.evaluate_condition(strategy['buy_condition'])
        buy_signals = buy_signals[mask]

        # Get sell signals
        sell_condition = strategy['sell_condition']
        sell_signals = self.evaluate_condition(sell_condition)
        sell_signals = sell_signals[mask]

        # Find all trade opportunities
        trades = []
        in_position = False
        entry_price = 0
        entry_date = None
        entry_idx = 0

        for i in range(len(df_test)):
            date = df_test.index[i]
            price = df_test['close'].iloc[i]
            high = df_test['high'].iloc[i]
            low = df_test['low'].iloc[i]

            if not in_position and buy_signals.iloc[i]:
                in_position = True
                entry_price = price
                entry_date = date
                entry_idx = i

            elif in_position:
                # Check exit conditions
                days_held = i - entry_idx

                if direction == 'long':
                    price_change = (price - entry_price) / entry_price
                    max_favorable = (df_test['high'].iloc[entry_idx:i+1].max() - entry_price) / entry_price
                    max_adverse = (entry_price - df_test['low'].iloc[entry_idx:i+1].min()) / entry_price
                else:
                    price_change = (entry_price - price) / entry_price
                    max_favorable = (entry_price - df_test['low'].iloc[entry_idx:i+1].min()) / entry_price
                    max_adverse = (df_test['high'].iloc[entry_idx:i+1].max() - entry_price) / entry_price

                # Exit on sell signal or after max holding period
                if sell_signals.iloc[i] or days_held >= 60:
                    trades.append({
                        'entry_date': entry_date,
                        'exit_date': date,
                        'entry_price': entry_price,
                        'exit_price': price,
                        'return': price_change,
                        'max_favorable': max_favorable,
                        'max_adverse': max_adverse,
                        'days_held': days_held,
                        'direction': direction
                    })
                    in_position = False

        if len(trades) == 0:
            return None

        trades_df = pd.DataFrame(trades)

        # Calculate base statistics
        win_rate = (trades_df['return'] > 0).mean()
        avg_return = trades_df['return'].mean()
        avg_winner = trades_df[trades_df['return'] > 0]['return'].mean() if (trades_df['return'] > 0).any() else 0
        avg_loser = abs(trades_df[trades_df['return'] <= 0]['return'].mean()) if (trades_df['return'] <= 0).any() else 0.01

        # Optimize parameters
        best_params = None
        best_equity = 0

        # Test different leverage, TP, SL combinations
        for base_leverage in [5, 10, 15, 20, 25, 30, 40, 50]:
            for tp_mult in [1.5, 2, 2.5, 3, 4, 5]:
                for sl_pct in [0.03, 0.05, 0.07, 0.10, 0.15]:
                    tp_pct = sl_pct * tp_mult

                    # Simulate with these parameters
                    equity = self.initial_capital
                    peak_equity = equity
                    max_drawdown = 0
                    trade_results = []

                    for _, trade in trades_df.iterrows():
                        # Kelly criterion for position sizing
                        if kelly_sizing and win_rate > 0 and avg_loser > 0:
                            kelly = (win_rate * avg_winner - (1 - win_rate) * avg_loser) / avg_winner
                            kelly = max(0.1, min(0.5, kelly))  # Cap between 10% and 50%
                        else:
                            kelly = 0.25

                        # Volatility adjustment
                        volatility = self.df.loc[trade['entry_date'], 'volatility'] if trade['entry_date'] in self.df.index else 0.5
                        vol_factor = max(0.3, min(1.5, 0.5 / (volatility + 0.1)))

                        # Adjust leverage based on volatility
                        adjusted_leverage = base_leverage * vol_factor
                        adjusted_leverage = max(5, min(50, adjusted_leverage))

                        # Position size
                        position_size = equity * kelly

                        # Calculate P&L with TP/SL
                        max_fav = trade['max_favorable']
                        max_adv = trade['max_adverse']
                        actual_return = trade['return']

                        # Trailing stop simulation
                        if trailing_stop and max_fav > tp_pct * 0.5:
                            # Lock in profits
                            locked_profit = max_fav - tp_pct * 0.3
                            if actual_return < locked_profit:
                                actual_return = locked_profit

                        # Apply TP/SL
                        if max_adv >= sl_pct:
                            actual_return = -sl_pct
                        elif max_fav >= tp_pct:
                            actual_return = tp_pct

                        # Calculate leveraged return
                        leveraged_return = actual_return * adjusted_leverage

                        # Cap at -95% (liquidation with some margin)
                        leveraged_return = max(-0.95, leveraged_return)

                        pnl = position_size * leveraged_return
                        equity += pnl

                        trade_results.append({
                            'pnl': pnl,
                            'return': leveraged_return,
                            'equity': equity
                        })

                        # Update drawdown
                        if equity > peak_equity:
                            peak_equity = equity
                        dd = (peak_equity - equity) / peak_equity
                        max_drawdown = max(max_drawdown, dd)

                        # Stop if blown up
                        if equity <= 0:
                            break

                    if equity > best_equity:
                        best_equity = equity
                        best_params = {
                            'leverage': base_leverage,
                            'tp_pct': tp_pct,
                            'sl_pct': sl_pct,
                            'trailing_stop': trailing_stop,
                            'kelly_sizing': kelly_sizing,
                            'final_equity': equity,
                            'total_return_pct': (equity - self.initial_capital) / self.initial_capital * 100,
                            'max_drawdown': max_drawdown * 100,
                            'num_trades': len(trades_df),
                            'win_rate': win_rate * 100,
                            'avg_trade_return': avg_return * 100,
                            'trade_results': trade_results
                        }

        return best_params


def run_full_analysis():
    """Run complete analysis and generate report"""
    print("=" * 60)
    print("BTC/USDT COMPREHENSIVE TRADING STRATEGY ANALYSIS")
    print("=" * 60)

    # Initialize
    engine = StrategyEngine('/home/user/zk-2048/trading_strategy/data')
    engine.load_data()
    engine.calculate_indicators()
    engine.generate_signals()
    engine.define_strategies()

    # Backtest all strategies
    print("\n" + "=" * 60)
    print("BACKTESTING ALL STRATEGIES")
    print("=" * 60)

    backtester = Backtester(engine.df)
    results = []

    for i, strategy in enumerate(engine.strategies):
        print(f"\nTesting strategy {i+1}/{len(engine.strategies)}: {strategy['name']}")

        result = backtester.backtest_strategy(strategy)

        if result:
            result['strategy_name'] = strategy['name']
            result['strategy_type'] = strategy['type']
            result['description'] = strategy['description']
            result['direction'] = strategy.get('direction', 'long')
            results.append(result)
            print(f"  Win Rate: {result['win_rate']:.1f}%, Return: {result['total_return_pct']:.1f}%, "
                  f"Trades: {result['num_trades']}, Max DD: {result['max_drawdown']:.1f}%")
        else:
            print(f"  No trades generated")

    # Sort by total return
    results.sort(key=lambda x: x['total_return_pct'], reverse=True)

    # Generate report
    print("\n" + "=" * 60)
    print("FINAL STRATEGY REPORT")
    print("=" * 60)

    print(f"\nTotal strategies tested: {len(engine.strategies)}")
    print(f"Strategies with trades: {len(results)}")

    # Filter for 70%+ win rate
    high_wr_results = [r for r in results if r['win_rate'] >= 70]
    print(f"Strategies with >= 70% win rate: {len(high_wr_results)}")

    # Filter for 10000%+ return
    mega_results = [r for r in results if r['total_return_pct'] >= 10000]
    print(f"Strategies with >= 10000% return: {len(mega_results)}")

    print("\n" + "-" * 60)
    print("TOP 20 STRATEGIES BY RETURN")
    print("-" * 60)

    for i, r in enumerate(results[:20]):
        print(f"\n{i+1}. {r['strategy_name']}")
        print(f"   Type: {r['strategy_type']} | Direction: {r['direction']}")
        print(f"   Description: {r['description']}")
        print(f"   Win Rate: {r['win_rate']:.1f}%")
        print(f"   Total Return: {r['total_return_pct']:,.1f}%")
        print(f"   Final Equity: ${r['final_equity']:,.2f}")
        print(f"   Trades: {r['num_trades']} | Max Drawdown: {r['max_drawdown']:.1f}%")
        print(f"   Optimal Leverage: {r['leverage']}x | TP: {r['tp_pct']*100:.1f}% | SL: {r['sl_pct']*100:.1f}%")

    # Save results
    results_df = pd.DataFrame([{
        'rank': i+1,
        'strategy_name': r['strategy_name'],
        'type': r['strategy_type'],
        'direction': r['direction'],
        'win_rate': r['win_rate'],
        'total_return_pct': r['total_return_pct'],
        'final_equity': r['final_equity'],
        'num_trades': r['num_trades'],
        'max_drawdown': r['max_drawdown'],
        'leverage': r['leverage'],
        'tp_pct': r['tp_pct'],
        'sl_pct': r['sl_pct'],
        'description': r['description']
    } for i, r in enumerate(results)])

    results_df.to_csv('/home/user/zk-2048/trading_strategy/reports/strategy_results.csv', index=False)
    print(f"\nResults saved to reports/strategy_results.csv")

    return results, engine


if __name__ == "__main__":
    results, engine = run_full_analysis()
