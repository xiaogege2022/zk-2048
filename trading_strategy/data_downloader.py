#!/usr/bin/env python3
"""
BTC/USDT Futures Data Downloader
Downloads historical kline data from Binance API with rate limiting
"""

import requests
import pandas as pd
import time
import os
from datetime import datetime, timedelta
import json

class BinanceDataDownloader:
    BASE_URL = "https://fapi.binance.com"
    SPOT_URL = "https://api.binance.com"

    INTERVALS = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '1h': 60,
        '4h': 240,
        '1d': 1440,
        '1w': 10080
    }

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.request_count = 0
        self.last_request_time = time.time()

    def _rate_limit(self):
        """Implement rate limiting to avoid API bans"""
        self.request_count += 1
        current_time = time.time()

        # Binance limit: 1200 requests per minute
        if self.request_count >= 1000:
            elapsed = current_time - self.last_request_time
            if elapsed < 60:
                sleep_time = 60 - elapsed + 5
                print(f"Rate limit reached, sleeping for {sleep_time:.1f}s...")
                time.sleep(sleep_time)
            self.request_count = 0
            self.last_request_time = time.time()
        else:
            # Add small delay between requests
            time.sleep(0.1)

    def get_klines(self, symbol, interval, start_time, end_time, limit=1500):
        """Fetch kline data from Binance Futures API"""
        self._rate_limit()

        url = f"{self.BASE_URL}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'startTime': start_time,
            'endTime': end_time,
            'limit': limit
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching klines: {e}")
            time.sleep(5)
            return []

    def get_funding_rate(self, symbol, start_time, end_time, limit=1000):
        """Fetch funding rate history"""
        self._rate_limit()

        url = f"{self.BASE_URL}/fapi/v1/fundingRate"
        params = {
            'symbol': symbol,
            'startTime': start_time,
            'endTime': end_time,
            'limit': limit
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching funding rate: {e}")
            time.sleep(5)
            return []

    def get_open_interest_hist(self, symbol, period, start_time, end_time, limit=500):
        """Fetch open interest history"""
        self._rate_limit()

        url = f"{self.BASE_URL}/futures/data/openInterestHist"
        params = {
            'symbol': symbol,
            'period': period,
            'startTime': start_time,
            'endTime': end_time,
            'limit': limit
        }

        try:
            response = requests.get(url, params=params, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as e:
            print(f"Error fetching OI: {e}")
            time.sleep(5)
            return []

    def download_all_klines(self, symbol, interval, start_date, end_date):
        """Download all klines for a given period"""
        print(f"Downloading {symbol} {interval} klines from {start_date} to {end_date}...")

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_data = []
        current_start = start_ts

        # Calculate batch size based on interval
        interval_minutes = self.INTERVALS.get(interval, 1)
        batch_ms = 1500 * interval_minutes * 60 * 1000  # 1500 candles per batch

        while current_start < end_ts:
            current_end = min(current_start + batch_ms, end_ts)

            data = self.get_klines(symbol, interval, current_start, current_end)

            if data:
                all_data.extend(data)
                print(f"  Downloaded {len(all_data)} candles so far...")
                current_start = data[-1][0] + 1  # Next ms after last candle
            else:
                current_start = current_end

            time.sleep(0.2)  # Extra delay between batches

        if all_data:
            df = pd.DataFrame(all_data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])

            # Convert types
            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)

            # Remove duplicates
            df = df.drop_duplicates(subset=['open_time'])
            df = df.sort_values('open_time').reset_index(drop=True)

            # Save to CSV
            filename = f"{self.data_dir}/{symbol}_{interval}.csv"
            df.to_csv(filename, index=False)
            print(f"  Saved {len(df)} candles to {filename}")

            return df

        return None

    def download_funding_rates(self, symbol, start_date, end_date):
        """Download all funding rate history"""
        print(f"Downloading {symbol} funding rates from {start_date} to {end_date}...")

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_data = []
        current_start = start_ts

        while current_start < end_ts:
            current_end = min(current_start + 1000 * 8 * 3600 * 1000, end_ts)  # ~333 days

            data = self.get_funding_rate(symbol, current_start, current_end)

            if data:
                all_data.extend(data)
                print(f"  Downloaded {len(all_data)} funding rates so far...")
                current_start = data[-1]['fundingTime'] + 1
            else:
                current_start = current_end

            time.sleep(0.2)

        if all_data:
            df = pd.DataFrame(all_data)
            df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
            df['fundingRate'] = df['fundingRate'].astype(float)
            df = df.drop_duplicates(subset=['fundingTime'])
            df = df.sort_values('fundingTime').reset_index(drop=True)

            filename = f"{self.data_dir}/{symbol}_funding_rate.csv"
            df.to_csv(filename, index=False)
            print(f"  Saved {len(df)} funding rates to {filename}")

            return df

        return None

    def download_open_interest(self, symbol, period, start_date, end_date):
        """Download open interest history"""
        print(f"Downloading {symbol} {period} OI from {start_date} to {end_date}...")

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)

        all_data = []
        current_start = start_ts

        # OI API limits
        period_ms = {
            '5m': 5 * 60 * 1000,
            '15m': 15 * 60 * 1000,
            '30m': 30 * 60 * 1000,
            '1h': 60 * 60 * 1000,
            '2h': 2 * 60 * 60 * 1000,
            '4h': 4 * 60 * 60 * 1000,
            '6h': 6 * 60 * 60 * 1000,
            '12h': 12 * 60 * 60 * 1000,
            '1d': 24 * 60 * 60 * 1000
        }

        batch_ms = 500 * period_ms.get(period, 24 * 60 * 60 * 1000)

        while current_start < end_ts:
            current_end = min(current_start + batch_ms, end_ts)

            data = self.get_open_interest_hist(symbol, period, current_start, current_end)

            if data:
                all_data.extend(data)
                print(f"  Downloaded {len(all_data)} OI records so far...")
                current_start = data[-1]['timestamp'] + 1
            else:
                current_start = current_end

            time.sleep(0.3)

        if all_data:
            df = pd.DataFrame(all_data)
            df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
            df['sumOpenInterest'] = df['sumOpenInterest'].astype(float)
            df['sumOpenInterestValue'] = df['sumOpenInterestValue'].astype(float)
            df = df.drop_duplicates(subset=['timestamp'])
            df = df.sort_values('timestamp').reset_index(drop=True)

            filename = f"{self.data_dir}/{symbol}_oi_{period}.csv"
            df.to_csv(filename, index=False)
            print(f"  Saved {len(df)} OI records to {filename}")

            return df

        return None


def download_fear_greed_index(data_dir="data"):
    """Download Fear & Greed Index from alternative.me"""
    print("Downloading Fear & Greed Index...")

    url = "https://api.alternative.me/fng/?limit=0&format=json"

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        data = response.json()['data']

        df = pd.DataFrame(data)
        df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='s')
        df['value'] = df['value'].astype(int)
        df = df[['timestamp', 'value', 'value_classification']]
        df = df.sort_values('timestamp').reset_index(drop=True)

        filename = f"{data_dir}/fear_greed_index.csv"
        df.to_csv(filename, index=False)
        print(f"  Saved {len(df)} Fear & Greed records to {filename}")

        return df
    except Exception as e:
        print(f"Error downloading Fear & Greed Index: {e}")
        return None


def main():
    """Main function to download all required data"""
    downloader = BinanceDataDownloader(data_dir="/home/user/zk-2048/trading_strategy/data")

    symbol = "BTCUSDT"
    # BTC futures started in September 2019 on Binance
    start_date = "2019-09-01"
    end_date = "2025-11-29"

    # Download klines for different intervals
    intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']

    for interval in intervals:
        try:
            downloader.download_all_klines(symbol, interval, start_date, end_date)
        except Exception as e:
            print(f"Error downloading {interval}: {e}")
        time.sleep(2)

    # Download funding rates
    try:
        downloader.download_funding_rates(symbol, start_date, end_date)
    except Exception as e:
        print(f"Error downloading funding rates: {e}")

    # Download Open Interest (only available for shorter history)
    try:
        downloader.download_open_interest(symbol, '1h', "2020-01-01", end_date)
        downloader.download_open_interest(symbol, '4h', "2020-01-01", end_date)
        downloader.download_open_interest(symbol, '1d', "2020-01-01", end_date)
    except Exception as e:
        print(f"Error downloading OI: {e}")

    # Download Fear & Greed Index
    download_fear_greed_index(data_dir="/home/user/zk-2048/trading_strategy/data")

    print("\n=== Data download complete! ===")


if __name__ == "__main__":
    main()
