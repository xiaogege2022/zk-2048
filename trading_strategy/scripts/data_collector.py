#!/usr/bin/env python3
"""
BTC/USDT 数据采集模块
Phase 1: 从币安API获取历史K线、资金费率、OI数据
"""

import requests
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import time
import os

DATA_DIR = "/home/user/zk-2048/trading_strategy/data"

class BinanceDataCollector:
    """币安数据采集器"""

    BASE_URL = "https://fapi.binance.com"

    def __init__(self):
        self.session = requests.Session()

    def get_klines(self, symbol="BTCUSDT", interval="1d", start_time=None, end_time=None, limit=1500):
        """获取K线数据"""
        url = f"{self.BASE_URL}/fapi/v1/klines"
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": limit
        }
        if start_time:
            params["startTime"] = int(start_time.timestamp() * 1000)
        if end_time:
            params["endTime"] = int(end_time.timestamp() * 1000)

        try:
            resp = self.session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            df = pd.DataFrame(data, columns=[
                'open_time', 'open', 'high', 'low', 'close', 'volume',
                'close_time', 'quote_volume', 'trades', 'taker_buy_volume',
                'taker_buy_quote_volume', 'ignore'
            ])

            df['open_time'] = pd.to_datetime(df['open_time'], unit='ms')
            df['close_time'] = pd.to_datetime(df['close_time'], unit='ms')

            for col in ['open', 'high', 'low', 'close', 'volume', 'quote_volume']:
                df[col] = df[col].astype(float)

            return df
        except Exception as e:
            print(f"获取K线失败: {e}")
            return None

    def get_all_klines(self, symbol="BTCUSDT", interval="1d", start_date="2019-09-08"):
        """获取从指定日期到现在的所有K线数据"""
        all_data = []
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.now()

        print(f"开始获取 {symbol} {interval} K线数据...")

        while start < end:
            df = self.get_klines(symbol, interval, start, end, limit=1500)
            if df is None or len(df) == 0:
                break

            all_data.append(df)
            print(f"  获取到 {len(df)} 条数据, 最新: {df['open_time'].iloc[-1]}")

            # 更新起始时间
            start = df['open_time'].iloc[-1] + timedelta(milliseconds=1)
            time.sleep(0.1)  # 避免API限制

        if all_data:
            result = pd.concat(all_data, ignore_index=True)
            result = result.drop_duplicates(subset=['open_time']).sort_values('open_time')
            print(f"总计获取 {len(result)} 条 {interval} K线数据")
            return result
        return None

    def get_funding_rate(self, symbol="BTCUSDT", start_date="2019-09-08"):
        """获取资金费率历史"""
        url = f"{self.BASE_URL}/fapi/v1/fundingRate"
        all_data = []
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.now()

        print(f"开始获取 {symbol} 资金费率数据...")

        while start < end:
            params = {
                "symbol": symbol,
                "startTime": int(start.timestamp() * 1000),
                "limit": 1000
            }

            try:
                resp = self.session.get(url, params=params, timeout=30)
                resp.raise_for_status()
                data = resp.json()

                if not data:
                    break

                all_data.extend(data)
                last_time = datetime.fromtimestamp(data[-1]['fundingTime'] / 1000)
                print(f"  获取到 {len(data)} 条数据, 最新: {last_time}")

                start = last_time + timedelta(seconds=1)
                time.sleep(0.1)
            except Exception as e:
                print(f"获取资金费率失败: {e}")
                break

        if all_data:
            df = pd.DataFrame(all_data)
            df['fundingTime'] = pd.to_datetime(df['fundingTime'], unit='ms')
            df['fundingRate'] = df['fundingRate'].astype(float)
            df = df.drop_duplicates(subset=['fundingTime']).sort_values('fundingTime')
            print(f"总计获取 {len(df)} 条资金费率数据")
            return df
        return None


class FearGreedCollector:
    """恐惧贪婪指数采集器"""

    URL = "https://api.alternative.me/fng/"

    def get_history(self, limit=2000):
        """获取历史恐惧贪婪指数"""
        print("开始获取恐惧贪婪指数数据...")

        try:
            resp = requests.get(self.URL, params={"limit": limit}, timeout=30)
            resp.raise_for_status()
            data = resp.json()

            if 'data' in data:
                df = pd.DataFrame(data['data'])
                df['timestamp'] = pd.to_datetime(df['timestamp'].astype(int), unit='s')
                df['value'] = df['value'].astype(int)
                df = df.sort_values('timestamp')
                print(f"总计获取 {len(df)} 条恐惧贪婪指数数据")
                return df
        except Exception as e:
            print(f"获取恐惧贪婪指数失败: {e}")
        return None


def collect_all_data():
    """采集所有数据"""
    os.makedirs(DATA_DIR, exist_ok=True)

    binance = BinanceDataCollector()
    fng = FearGreedCollector()

    # 1. 获取多周期K线数据
    intervals = ['1d', '4h', '1h']  # 先获取主要周期
    for interval in intervals:
        df = binance.get_all_klines(interval=interval)
        if df is not None:
            filename = f"{DATA_DIR}/BTCUSDT_{interval}.csv"
            df.to_csv(filename, index=False)
            print(f"保存: {filename}")
        time.sleep(1)

    # 2. 获取资金费率
    funding = binance.get_funding_rate()
    if funding is not None:
        funding.to_csv(f"{DATA_DIR}/funding_rate.csv", index=False)
        print(f"保存: {DATA_DIR}/funding_rate.csv")

    # 3. 获取恐惧贪婪指数
    fng_data = fng.get_history()
    if fng_data is not None:
        fng_data.to_csv(f"{DATA_DIR}/fear_greed_index.csv", index=False)
        print(f"保存: {DATA_DIR}/fear_greed_index.csv")

    print("\n数据采集完成!")
    return True


if __name__ == "__main__":
    collect_all_data()
