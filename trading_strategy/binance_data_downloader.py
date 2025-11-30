#!/usr/bin/env python3
"""
Binance Public Data Downloader
Downloads historical kline data from data.binance.vision
"""

import os
import requests
import zipfile
import pandas as pd
from datetime import datetime, timedelta
from io import BytesIO
import time

class BinancePublicDataDownloader:
    """Download historical data from Binance public data repository"""

    # Base URLs
    SPOT_BASE = "https://data.binance.vision/data/spot/monthly/klines"
    FUTURES_BASE = "https://data.binance.vision/data/futures/um/monthly/klines"

    # Daily data URLs (for recent data not yet in monthly files)
    SPOT_DAILY_BASE = "https://data.binance.vision/data/spot/daily/klines"
    FUTURES_DAILY_BASE = "https://data.binance.vision/data/futures/um/daily/klines"

    def __init__(self, data_dir="data"):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)

    def download_monthly_klines(self, symbol, interval, year, month, use_futures=True):
        """Download monthly kline data"""
        base_url = self.FUTURES_BASE if use_futures else self.SPOT_BASE
        filename = f"{symbol}-{interval}-{year}-{month:02d}.zip"
        url = f"{base_url}/{symbol}/{interval}/{filename}"

        try:
            print(f"  Downloading {filename}...")
            response = requests.get(url, timeout=60)

            if response.status_code == 200:
                # Extract CSV from ZIP
                with zipfile.ZipFile(BytesIO(response.content)) as z:
                    csv_name = z.namelist()[0]
                    with z.open(csv_name) as f:
                        df = pd.read_csv(f, header=None)
                        return df
            elif response.status_code == 404:
                print(f"    Not found: {filename}")
                return None
            else:
                print(f"    Error {response.status_code}: {filename}")
                return None

        except Exception as e:
            print(f"    Exception: {e}")
            return None

    def download_daily_klines(self, symbol, interval, date_str, use_futures=True):
        """Download daily kline data for recent dates"""
        base_url = self.FUTURES_DAILY_BASE if use_futures else self.SPOT_DAILY_BASE
        filename = f"{symbol}-{interval}-{date_str}.zip"
        url = f"{base_url}/{symbol}/{interval}/{filename}"

        try:
            response = requests.get(url, timeout=60)

            if response.status_code == 200:
                with zipfile.ZipFile(BytesIO(response.content)) as z:
                    csv_name = z.namelist()[0]
                    with z.open(csv_name) as f:
                        df = pd.read_csv(f, header=None)
                        return df
            return None

        except Exception as e:
            return None

    def download_all_klines(self, symbol, interval, start_year, start_month,
                            end_year, end_month, use_futures=True):
        """Download all klines for a date range"""
        print(f"\n{'='*60}")
        print(f"Downloading {symbol} {interval} klines ({start_year}-{start_month:02d} to {end_year}-{end_month:02d})")
        print(f"Source: {'Futures' if use_futures else 'Spot'}")
        print(f"{'='*60}")

        all_data = []

        # Iterate through months
        current_year = start_year
        current_month = start_month

        while (current_year < end_year) or (current_year == end_year and current_month <= end_month):
            df = self.download_monthly_klines(symbol, interval, current_year, current_month, use_futures)

            if df is not None and len(df) > 0:
                all_data.append(df)
                print(f"    ✓ {current_year}-{current_month:02d}: {len(df)} candles")

            # Move to next month
            current_month += 1
            if current_month > 12:
                current_month = 1
                current_year += 1

            time.sleep(0.3)  # Be nice to the server

        if all_data:
            # Combine all data
            combined = pd.concat(all_data, ignore_index=True)

            # Set column names based on Binance format
            columns = [
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ]
            combined.columns = columns[:len(combined.columns)]

            # Convert types
            combined['open_time'] = pd.to_datetime(combined['open_time'], unit='ms')
            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                if col in combined.columns:
                    combined[col] = pd.to_numeric(combined[col], errors='coerce')

            # Remove duplicates and sort
            combined = combined.drop_duplicates(subset=['open_time'])
            combined = combined.sort_values('open_time').reset_index(drop=True)

            # Save to CSV
            market_type = "futures" if use_futures else "spot"
            filename = f"{self.data_dir}/{symbol}_{interval}_{market_type}.csv"
            combined.to_csv(filename, index=False)

            print(f"\n✓ Saved {len(combined)} candles to {filename}")
            print(f"  Date range: {combined['open_time'].min()} to {combined['open_time'].max()}")

            return combined

        return None


def main():
    """Download all required historical data"""
    downloader = BinancePublicDataDownloader(
        data_dir="/home/user/zk-2048/trading_strategy/data"
    )

    symbol = "BTCUSDT"

    # Date range: 2019-09 to 2025-11
    # Note: Futures data starts from 2019-09, Spot from earlier
    start_year, start_month = 2019, 9
    end_year, end_month = 2025, 11

    # Intervals to download
    intervals = ['5m', '15m', '1h', '4h', '1d', '1w']

    print("\n" + "="*70)
    print("BINANCE HISTORICAL DATA DOWNLOADER")
    print("Source: data.binance.vision (Public Data Repository)")
    print("="*70)

    results = {}

    for interval in intervals:
        try:
            df = downloader.download_all_klines(
                symbol=symbol,
                interval=interval,
                start_year=start_year,
                start_month=start_month,
                end_year=end_year,
                end_month=end_month,
                use_futures=True  # Use futures data
            )

            if df is not None:
                results[interval] = len(df)
            else:
                results[interval] = 0

        except Exception as e:
            print(f"Error downloading {interval}: {e}")
            results[interval] = 0

        time.sleep(1)  # Pause between intervals

    # Summary
    print("\n" + "="*70)
    print("DOWNLOAD SUMMARY")
    print("="*70)
    for interval, count in results.items():
        status = "✓" if count > 0 else "✗"
        print(f"  {status} {interval}: {count:,} candles")

    print("\n✓ All downloads complete!")
    print(f"Data saved to: {downloader.data_dir}/")


if __name__ == "__main__":
    main()
