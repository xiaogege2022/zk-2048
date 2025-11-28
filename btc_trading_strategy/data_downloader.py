#!/usr/bin/env python3
"""
Binance BTC/USDT Futures Data Downloader
Downloads historical data while respecting API rate limits
"""

import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Optional
import json

class BinanceDataDownloader:
    """Download historical data from Binance Futures API"""

    BASE_URL = "https://fapi.binance.com"
    SPOT_URL = "https://api.binance.com"

    # Rate limit: 1200 requests per minute, we'll be conservative
    REQUEST_DELAY = 0.1  # 100ms between requests

    INTERVALS = {
        '1m': 1,
        '5m': 5,
        '15m': 15,
        '1h': 60,
        '4h': 240,
        '1d': 1440,
        '1w': 10080
    }

    def __init__(self, data_dir: str = "data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.session = requests.Session()

    def _request_with_retry(self, url: str, params: dict, max_retries: int = 5) -> Optional[dict]:
        """Make request with exponential backoff retry"""
        for attempt in range(max_retries):
            try:
                response = self.session.get(url, params=params, timeout=30)

                if response.status_code == 429:  # Rate limited
                    wait_time = 2 ** attempt * 10
                    print(f"Rate limited, waiting {wait_time}s...")
                    time.sleep(wait_time)
                    continue

                if response.status_code == 200:
                    return response.json()

                print(f"Error {response.status_code}: {response.text}")
                time.sleep(2 ** attempt)

            except Exception as e:
                print(f"Request error: {e}, retrying...")
                time.sleep(2 ** attempt)

        return None

    def download_klines(self, symbol: str = "BTCUSDT", interval: str = "1d",
                       start_date: str = "2019-09-01", end_date: str = None) -> pd.DataFrame:
        """
        Download kline/candlestick data

        Args:
            symbol: Trading pair (default BTCUSDT)
            interval: Kline interval (1m, 5m, 15m, 1h, 4h, 1d, 1w)
            start_date: Start date string (YYYY-MM-DD)
            end_date: End date string (YYYY-MM-DD), defaults to now
        """
        endpoint = f"{self.BASE_URL}/fapi/v1/klines"

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        if end_date:
            end_ts = int(datetime.strptime(end_date, "%Y-%m-%d").timestamp() * 1000)
        else:
            end_ts = int(datetime.now().timestamp() * 1000)

        all_data = []
        current_ts = start_ts
        batch_size = 1500  # Max limit per request

        print(f"Downloading {symbol} {interval} data from {start_date}...")

        while current_ts < end_ts:
            params = {
                'symbol': symbol,
                'interval': interval,
                'startTime': current_ts,
                'endTime': end_ts,
                'limit': batch_size
            }

            data = self._request_with_retry(endpoint, params)

            if not data or len(data) == 0:
                break

            all_data.extend(data)

            # Move to next batch
            last_ts = data[-1][0]
            if last_ts == current_ts:
                break
            current_ts = last_ts + 1

            time.sleep(self.REQUEST_DELAY)

            if len(all_data) % 10000 == 0:
                print(f"  Downloaded {len(all_data)} candles...")

        if not all_data:
            print(f"No data downloaded for {symbol} {interval}")
            return pd.DataFrame()

        # Convert to DataFrame
        df = pd.DataFrame(all_data, columns=[
            'open_time', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
            'taker_buy_quote_volume', 'ignore'
        ])

        # Convert types
        df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
        df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

        for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume',
                    'taker_buy_volume', 'taker_buy_quote_volume']:
            df[col] = df[col].astype(float)

        df['trades'] = df['trades'].astype(int)
        df = df.drop(columns=['ignore'])
        df = df.drop_duplicates(subset=['open_time']).sort_values('open_time').reset_index(drop=True)

        print(f"  Downloaded {len(df)} candles for {symbol} {interval}")
        return df

    def download_funding_rate(self, symbol: str = "BTCUSDT",
                              start_date: str = "2019-09-01") -> pd.DataFrame:
        """Download historical funding rate data"""
        endpoint = f"{self.BASE_URL}/fapi/v1/fundingRate"

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.now().timestamp() * 1000)

        all_data = []
        current_ts = start_ts

        print(f"Downloading {symbol} funding rate data...")

        while current_ts < end_ts:
            params = {
                'symbol': symbol,
                'startTime': current_ts,
                'limit': 1000
            }

            data = self._request_with_retry(endpoint, params)

            if not data or len(data) == 0:
                break

            all_data.extend(data)
            current_ts = data[-1]['fundingTime'] + 1

            time.sleep(self.REQUEST_DELAY)

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
        df['fundingRate'] = df['fundingRate'].astype(float)
        df = df.drop_duplicates(subset=['fundingTime']).sort_values('fundingTime').reset_index(drop=True)

        print(f"  Downloaded {len(df)} funding rate records")
        return df

    def download_open_interest_hist(self, symbol: str = "BTCUSDT",
                                     period: str = "1h",
                                     start_date: str = "2020-01-01") -> pd.DataFrame:
        """Download historical open interest data"""
        endpoint = f"{self.BASE_URL}/futures/data/openInterestHist"

        start_ts = int(datetime.strptime(start_date, "%Y-%m-%d").timestamp() * 1000)
        end_ts = int(datetime.now().timestamp() * 1000)

        all_data = []
        current_ts = start_ts

        print(f"Downloading {symbol} open interest data (period={period})...")

        # API only returns 30 days at a time for some periods
        while current_ts < end_ts:
            params = {
                'symbol': symbol,
                'period': period,
                'startTime': current_ts,
                'limit': 500
            }

            data = self._request_with_retry(endpoint, params)

            if not data or len(data) == 0:
                # Move forward 30 days if no data
                current_ts += 30 * 24 * 60 * 60 * 1000
                continue

            all_data.extend(data)
            current_ts = data[-1]['timestamp'] + 1

            time.sleep(self.REQUEST_DELAY * 2)  # Be more conservative

        if not all_data:
            return pd.DataFrame()

        df = pd.DataFrame(all_data)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        df['sumOpenInterest'] = df['sumOpenInterest'].astype(float)
        df['sumOpenInterestValue'] = df['sumOpenInterestValue'].astype(float)
        df = df.drop_duplicates(subset=['timestamp']).sort_values('timestamp').reset_index(drop=True)

        print(f"  Downloaded {len(df)} OI records")
        return df

    def download_fear_greed_index(self, limit: int = 3000) -> pd.DataFrame:
        """Download Fear & Greed Index from alternative.me"""
        url = "https://api.alternative.me/fng/"

        print("Downloading Fear & Greed Index...")

        params = {'limit': limit, 'format': 'json'}

        try:
            response = requests.get(url, params=params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                df = pd.DataFrame(data['data'])
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='s')
                df['value'] = df['value'].astype(int)
                df = df.sort_values('timestamp').reset_index(drop=True)
                print(f"  Downloaded {len(df)} Fear & Greed records")
                return df
        except Exception as e:
            print(f"Error downloading Fear & Greed Index: {e}")

        return pd.DataFrame()

    def download_all_data(self, start_date: str = "2019-09-01"):
        """Download all required data"""

        intervals = ['1m', '5m', '15m', '1h', '4h', '1d', '1w']

        # Download klines for all intervals
        for interval in intervals:
            print(f"\n{'='*50}")
            print(f"Processing {interval} interval...")

            df = self.download_klines("BTCUSDT", interval, start_date)
            if not df.empty:
                filepath = os.path.join(self.data_dir, f"BTCUSDT_{interval}.csv")
                df.to_csv(filepath, index=False)
                print(f"  Saved to {filepath}")

        # Download funding rate
        print(f"\n{'='*50}")
        df_funding = self.download_funding_rate("BTCUSDT", start_date)
        if not df_funding.empty:
            filepath = os.path.join(self.data_dir, "BTCUSDT_funding_rate.csv")
            df_funding.to_csv(filepath, index=False)
            print(f"  Saved to {filepath}")

        # Download open interest
        print(f"\n{'='*50}")
        df_oi = self.download_open_interest_hist("BTCUSDT", "1h", "2020-01-01")
        if not df_oi.empty:
            filepath = os.path.join(self.data_dir, "BTCUSDT_open_interest.csv")
            df_oi.to_csv(filepath, index=False)
            print(f"  Saved to {filepath}")

        # Download Fear & Greed Index
        print(f"\n{'='*50}")
        df_fgi = self.download_fear_greed_index()
        if not df_fgi.empty:
            filepath = os.path.join(self.data_dir, "fear_greed_index.csv")
            df_fgi.to_csv(filepath, index=False)
            print(f"  Saved to {filepath}")

        print(f"\n{'='*50}")
        print("All data download complete!")

        # Print summary
        print("\nData Summary:")
        for f in os.listdir(self.data_dir):
            if f.endswith('.csv'):
                filepath = os.path.join(self.data_dir, f)
                df = pd.read_csv(filepath)
                print(f"  {f}: {len(df)} rows")


if __name__ == "__main__":
    downloader = BinanceDataDownloader(data_dir="/home/user/zk-2048/btc_trading_strategy/data")

    # Start from 2017-01-01 for maximum history (Binance futures started 2019-09)
    downloader.download_all_data(start_date="2019-09-01")
