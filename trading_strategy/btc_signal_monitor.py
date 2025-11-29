#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
BTC/USDT 实时交易信号监控器
自动监控币安K线数据，检测交易信号并推送到 Telegram 和 Discord
"""

import requests
import time
import datetime
import json
import sys
import os
from dataclasses import dataclass
from typing import Optional, List, Dict
from enum import Enum

# ============================================
# 配置区域
# ============================================

# Telegram 配置
TELEGRAM_BOT_TOKEN = "8402682954:AAH4FnWpdZ4t1tQAFKcg2GXjMtzdfSd7P8A"
TELEGRAM_CHAT_ID = "6935870343"

# Discord 配置
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1444323268600266773/i5WXa-v66RrHnl6SP6IVXw4vtABzavxxeOZo6OJAk_gRMV-Khx88wWRSE_aNQ4kSqtEm"

# 监控间隔（秒）
CHECK_INTERVAL = 60  # 每分钟检查一次

# ============================================
# 信号类型
# ============================================

class SignalType(Enum):
    LONG = "做多"
    SHORT = "做空"

@dataclass
class TradingSignal:
    signal_type: SignalType
    strategy_name: str
    win_rate: float
    entry_price: float
    take_profit_pct: float
    stop_loss_pct: float
    leverage: int
    confidence: str
    description: str

# ============================================
# 策略配置 - 胜率 > 50% 的所有策略
# ============================================

STRATEGIES = {
    # EMA 交叉策略
    "EMA_7_25_Golden": {"win_rate": 80.0, "tp": 15.0, "sl": 7.0, "leverage": 25, "type": "LONG", "desc": "EMA7上穿EMA25金叉信号"},
    "EMA_7_25_Death": {"win_rate": 65.0, "tp": 10.0, "sl": 5.0, "leverage": 20, "type": "SHORT", "desc": "EMA7下穿EMA25死叉信号"},
    "EMA_50_200_Golden": {"win_rate": 71.4, "tp": 25.0, "sl": 10.0, "leverage": 35, "type": "LONG", "desc": "EMA50上穿EMA200黄金交叉"},
    "EMA_50_200_Death": {"win_rate": 68.0, "tp": 15.0, "sl": 7.0, "leverage": 20, "type": "SHORT", "desc": "EMA50下穿EMA200死亡交叉"},

    # RSI 策略
    "RSI_Oversold": {"win_rate": 78.0, "tp": 15.0, "sl": 7.0, "leverage": 20, "type": "LONG", "desc": "RSI极度超卖(<20)反弹"},
    "RSI_Overbought": {"win_rate": 72.0, "tp": 10.0, "sl": 5.0, "leverage": 15, "type": "SHORT", "desc": "RSI极度超买(>80)回调"},

    # MACD 策略
    "MACD_Golden": {"win_rate": 65.0, "tp": 12.0, "sl": 6.0, "leverage": 20, "type": "LONG", "desc": "MACD金叉信号"},
    "MACD_Death": {"win_rate": 62.0, "tp": 10.0, "sl": 5.0, "leverage": 15, "type": "SHORT", "desc": "MACD死叉信号"},

    # 突破策略
    "Breakout_Buy": {"win_rate": 78.1, "tp": 12.0, "sl": 6.0, "leverage": 30, "type": "LONG", "desc": "7天盘整后突破买入"},

    # Pin Bar 策略
    "Bullish_Pin_Bar": {"win_rate": 71.4, "tp": 15.0, "sl": 8.0, "leverage": 25, "type": "LONG", "desc": "看涨Pin Bar形态"},
    "Bearish_Pin_Bar": {"win_rate": 65.0, "tp": 12.0, "sl": 6.0, "leverage": 20, "type": "SHORT", "desc": "看跌Pin Bar形态"},

    # 恐惧贪婪指数
    "Fear_Extreme": {"win_rate": 78.0, "tp": 20.0, "sl": 10.0, "leverage": 25, "type": "LONG", "desc": "恐惧贪婪指数<10极度恐惧"},
    "Greed_Extreme": {"win_rate": 65.0, "tp": 15.0, "sl": 7.0, "leverage": 15, "type": "SHORT", "desc": "恐惧贪婪指数>90极度贪婪"},

    # 闪崩策略
    "Flash_Crash": {"win_rate": 66.7, "tp": 20.0, "sl": 10.0, "leverage": 20, "type": "LONG", "desc": "7日暴跌超15%抄底"},

    # 成交量策略
    "Volume_Spike_Up": {"win_rate": 68.0, "tp": 12.0, "sl": 6.0, "leverage": 20, "type": "LONG", "desc": "放量上涨突破"},
    "Volume_Spike_Down": {"win_rate": 64.0, "tp": 10.0, "sl": 5.0, "leverage": 15, "type": "SHORT", "desc": "放量下跌破位"},
}


class BinanceAPI:
    """币安公共API"""

    BASE_URL = "https://api.binance.com/api/v3"

    @staticmethod
    def get_klines(symbol: str = "BTCUSDT", interval: str = "1h", limit: int = 200) -> List[Dict]:
        """获取K线数据"""
        url = f"{BinanceAPI.BASE_URL}/klines"
        params = {"symbol": symbol, "interval": interval, "limit": limit}
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                data = response.json()
                klines = []
                for k in data:
                    klines.append({
                        "timestamp": k[0],
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5])
                    })
                return klines
        except Exception as e:
            print(f"获取K线失败: {e}")
        return []

    @staticmethod
    def get_price(symbol: str = "BTCUSDT") -> Optional[float]:
        """获取当前价格"""
        url = f"{BinanceAPI.BASE_URL}/ticker/price"
        params = {"symbol": symbol}
        try:
            response = requests.get(url, params=params, timeout=10)
            if response.status_code == 200:
                return float(response.json()["price"])
        except Exception as e:
            print(f"获取价格失败: {e}")
        return None


class FearGreedAPI:
    """恐惧贪婪指数API"""

    @staticmethod
    def get_index() -> Optional[int]:
        try:
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return int(response.json()["data"][0]["value"])
        except:
            pass
        return None


class TechnicalAnalysis:
    """技术分析指标计算"""

    @staticmethod
    def calculate_ema(prices: List[float], period: int) -> List[float]:
        """计算EMA"""
        if len(prices) < period:
            return []

        ema = []
        multiplier = 2 / (period + 1)
        sma = sum(prices[:period]) / period
        ema.append(sma)

        for i in range(period, len(prices)):
            new_ema = (prices[i] - ema[-1]) * multiplier + ema[-1]
            ema.append(new_ema)

        return ema

    @staticmethod
    def calculate_rsi(prices: List[float], period: int = 14) -> List[float]:
        """计算RSI"""
        if len(prices) < period + 1:
            return []

        rsi = []
        gains = []
        losses = []

        for i in range(1, len(prices)):
            change = prices[i] - prices[i-1]
            gains.append(max(0, change))
            losses.append(max(0, -change))

        for i in range(period - 1, len(gains)):
            avg_gain = sum(gains[i-period+1:i+1]) / period
            avg_loss = sum(losses[i-period+1:i+1]) / period

            if avg_loss == 0:
                rsi.append(100)
            else:
                rs = avg_gain / avg_loss
                rsi.append(100 - (100 / (1 + rs)))

        return rsi

    @staticmethod
    def calculate_macd(prices: List[float]) -> Dict:
        """计算MACD"""
        ema12 = TechnicalAnalysis.calculate_ema(prices, 12)
        ema26 = TechnicalAnalysis.calculate_ema(prices, 26)

        if not ema12 or not ema26:
            return {"macd": [], "signal": [], "histogram": []}

        # 对齐长度
        min_len = min(len(ema12), len(ema26))
        ema12 = ema12[-min_len:]
        ema26 = ema26[-min_len:]

        macd_line = [ema12[i] - ema26[i] for i in range(len(ema12))]
        signal_line = TechnicalAnalysis.calculate_ema(macd_line, 9)

        if not signal_line:
            return {"macd": macd_line, "signal": [], "histogram": []}

        # 对齐
        min_len = min(len(macd_line), len(signal_line))
        macd_line = macd_line[-min_len:]
        signal_line = signal_line[-min_len:]
        histogram = [macd_line[i] - signal_line[i] for i in range(len(macd_line))]

        return {"macd": macd_line, "signal": signal_line, "histogram": histogram}


class SignalDetector:
    """信号检测器"""

    def __init__(self):
        self.last_signals = {}  # 用于避免重复信号
        self.signal_cooldown = 3600  # 同一信号1小时内不重复

    def detect_signals(self, klines: List[Dict], fear_greed: Optional[int]) -> List[TradingSignal]:
        """检测所有交易信号"""
        signals = []

        if len(klines) < 200:
            return signals

        prices = [k["close"] for k in klines]
        volumes = [k["volume"] for k in klines]
        highs = [k["high"] for k in klines]
        lows = [k["low"] for k in klines]
        current_price = prices[-1]

        # 计算指标
        ema7 = TechnicalAnalysis.calculate_ema(prices, 7)
        ema25 = TechnicalAnalysis.calculate_ema(prices, 25)
        ema50 = TechnicalAnalysis.calculate_ema(prices, 50)
        ema200 = TechnicalAnalysis.calculate_ema(prices, 200)
        rsi = TechnicalAnalysis.calculate_rsi(prices, 14)
        macd_data = TechnicalAnalysis.calculate_macd(prices)

        # 1. EMA 7/25 交叉
        if len(ema7) >= 2 and len(ema25) >= 2:
            if ema7[-2] <= ema25[-2] and ema7[-1] > ema25[-1]:
                signals.append(self._create_signal("EMA_7_25_Golden", current_price))
            elif ema7[-2] >= ema25[-2] and ema7[-1] < ema25[-1]:
                signals.append(self._create_signal("EMA_7_25_Death", current_price))

        # 2. EMA 50/200 交叉
        if len(ema50) >= 2 and len(ema200) >= 2:
            if ema50[-2] <= ema200[-2] and ema50[-1] > ema200[-1]:
                signals.append(self._create_signal("EMA_50_200_Golden", current_price))
            elif ema50[-2] >= ema200[-2] and ema50[-1] < ema200[-1]:
                signals.append(self._create_signal("EMA_50_200_Death", current_price))

        # 3. RSI 极端值
        if rsi:
            current_rsi = rsi[-1]
            if current_rsi < 20:
                signals.append(self._create_signal("RSI_Oversold", current_price, f"RSI={current_rsi:.1f}"))
            elif current_rsi > 80:
                signals.append(self._create_signal("RSI_Overbought", current_price, f"RSI={current_rsi:.1f}"))

        # 4. MACD 交叉
        if len(macd_data["macd"]) >= 2 and len(macd_data["signal"]) >= 2:
            macd = macd_data["macd"]
            signal = macd_data["signal"]
            if macd[-2] <= signal[-2] and macd[-1] > signal[-1]:
                signals.append(self._create_signal("MACD_Golden", current_price))
            elif macd[-2] >= signal[-2] and macd[-1] < signal[-1]:
                signals.append(self._create_signal("MACD_Death", current_price))

        # 5. 恐惧贪婪指数
        if fear_greed is not None:
            if fear_greed <= 10:
                signals.append(self._create_signal("Fear_Extreme", current_price, f"F&G={fear_greed}"))
            elif fear_greed >= 90:
                signals.append(self._create_signal("Greed_Extreme", current_price, f"F&G={fear_greed}"))

        # 6. 7日价格变化 (闪崩检测)
        if len(prices) >= 168:  # 7天 * 24小时
            price_7d_ago = prices[-168]
            change_7d = (current_price - price_7d_ago) / price_7d_ago * 100
            if change_7d <= -15:
                signals.append(self._create_signal("Flash_Crash", current_price, f"7日跌幅={change_7d:.1f}%"))

        # 7. Pin Bar 检测
        if len(klines) >= 2:
            last_candle = klines[-1]
            body = abs(last_candle["close"] - last_candle["open"])
            upper_wick = last_candle["high"] - max(last_candle["close"], last_candle["open"])
            lower_wick = min(last_candle["close"], last_candle["open"]) - last_candle["low"]

            if lower_wick > body * 2 and lower_wick > upper_wick * 2:
                signals.append(self._create_signal("Bullish_Pin_Bar", current_price))
            elif upper_wick > body * 2 and upper_wick > lower_wick * 2:
                signals.append(self._create_signal("Bearish_Pin_Bar", current_price))

        # 8. 成交量突破
        if len(volumes) >= 20:
            avg_volume = sum(volumes[-20:-1]) / 19
            current_volume = volumes[-1]
            price_change = (prices[-1] - prices[-2]) / prices[-2] * 100

            if current_volume > avg_volume * 2:
                if price_change > 1:
                    signals.append(self._create_signal("Volume_Spike_Up", current_price, f"量比={current_volume/avg_volume:.1f}"))
                elif price_change < -1:
                    signals.append(self._create_signal("Volume_Spike_Down", current_price, f"量比={current_volume/avg_volume:.1f}"))

        # 9. 盘整突破
        if len(prices) >= 168:
            prices_7d = prices[-168:]
            high_7d = max(prices_7d[:-1])
            low_7d = min(prices_7d[:-1])
            range_pct = (high_7d - low_7d) / low_7d * 100

            if range_pct < 5 and current_price > high_7d:
                signals.append(self._create_signal("Breakout_Buy", current_price))

        # 过滤重复信号
        filtered_signals = []
        current_time = time.time()
        for signal in signals:
            key = signal.strategy_name
            if key not in self.last_signals or (current_time - self.last_signals[key]) > self.signal_cooldown:
                self.last_signals[key] = current_time
                filtered_signals.append(signal)

        return filtered_signals

    def _create_signal(self, strategy_key: str, price: float, extra_info: str = "") -> TradingSignal:
        """创建交易信号"""
        config = STRATEGIES[strategy_key]

        signal_type = SignalType.LONG if config["type"] == "LONG" else SignalType.SHORT

        # 计算信号强度
        win_rate = config["win_rate"]
        if win_rate >= 75:
            confidence = "⭐⭐⭐⭐⭐ 极强"
        elif win_rate >= 70:
            confidence = "⭐⭐⭐⭐ 强"
        elif win_rate >= 65:
            confidence = "⭐⭐⭐ 中等"
        else:
            confidence = "⭐⭐ 一般"

        desc = config["desc"]
        if extra_info:
            desc += f" ({extra_info})"

        return TradingSignal(
            signal_type=signal_type,
            strategy_name=strategy_key.replace("_", " "),
            win_rate=win_rate,
            entry_price=price,
            take_profit_pct=config["tp"],
            stop_loss_pct=config["sl"],
            leverage=config["leverage"],
            confidence=confidence,
            description=desc
        )


class NotificationSender:
    """通知发送器 - 同时推送到 Telegram 和 Discord"""

    def __init__(self):
        self.tg_token = TELEGRAM_BOT_TOKEN
        self.tg_chat_id = TELEGRAM_CHAT_ID
        self.discord_webhook = DISCORD_WEBHOOK_URL

    def send_signal(self, signal: TradingSignal) -> bool:
        """发送信号到所有渠道"""
        tg_success = self._send_telegram(signal)
        discord_success = self._send_discord(signal)
        return tg_success or discord_success

    def _send_telegram(self, signal: TradingSignal) -> bool:
        """发送到 Telegram"""
        if signal.signal_type == SignalType.LONG:
            direction = "🟢 做多 LONG"
            tp_price = signal.entry_price * (1 + signal.take_profit_pct / 100)
            sl_price = signal.entry_price * (1 - signal.stop_loss_pct / 100)
        else:
            direction = "🔴 做空 SHORT"
            tp_price = signal.entry_price * (1 - signal.take_profit_pct / 100)
            sl_price = signal.entry_price * (1 + signal.stop_loss_pct / 100)

        message = f"""🚨 <b>BTC/USDT 交易信号</b>
━━━━━━━━━━━━━━━━━━━━

<b>{direction}</b>

📊 <b>策略:</b> {signal.strategy_name}
📈 <b>胜率:</b> {signal.win_rate:.1f}%
💪 <b>信号强度:</b> {signal.confidence}

━━━━━━━━━━━━━━━━━━━━

💰 <b>入场价格:</b> ${signal.entry_price:,.2f}
✅ <b>止盈:</b> ${tp_price:,.2f} (+{signal.take_profit_pct:.1f}%)
❌ <b>止损:</b> ${sl_price:,.2f} (-{signal.stop_loss_pct:.1f}%)
⚡ <b>杠杆倍数:</b> {signal.leverage}倍

━━━━━━━━━━━━━━━━━━━━

📝 <b>策略说明:</b> {signal.description}
🕐 <b>时间:</b> {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

⚠️ <i>风险提示: 仅供参考，请自行判断</i>"""

        try:
            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            payload = {
                "chat_id": self.tg_chat_id,
                "text": message,
                "parse_mode": "HTML"
            }
            response = requests.post(url, json=payload, timeout=10)
            return response.status_code == 200
        except Exception as e:
            print(f"Telegram发送失败: {e}")
            return False

    def _send_discord(self, signal: TradingSignal) -> bool:
        """发送到 Discord"""
        if signal.signal_type == SignalType.LONG:
            direction = "🟢 **做多 LONG**"
            color = 0x00FF00
            tp_price = signal.entry_price * (1 + signal.take_profit_pct / 100)
            sl_price = signal.entry_price * (1 - signal.stop_loss_pct / 100)
        else:
            direction = "🔴 **做空 SHORT**"
            color = 0xFF0000
            tp_price = signal.entry_price * (1 - signal.take_profit_pct / 100)
            sl_price = signal.entry_price * (1 + signal.stop_loss_pct / 100)

        embed = {
            "title": "🚨 BTC/USDT 交易信号",
            "color": color,
            "fields": [
                {"name": "📊 方向", "value": direction, "inline": True},
                {"name": "📈 策略", "value": signal.strategy_name, "inline": True},
                {"name": "🎯 胜率", "value": f"**{signal.win_rate:.1f}%**", "inline": True},
                {"name": "💰 入场价格", "value": f"${signal.entry_price:,.2f}", "inline": True},
                {"name": "✅ 止盈", "value": f"${tp_price:,.2f} (+{signal.take_profit_pct:.1f}%)", "inline": True},
                {"name": "❌ 止损", "value": f"${sl_price:,.2f} (-{signal.stop_loss_pct:.1f}%)", "inline": True},
                {"name": "⚡ 杠杆倍数", "value": f"**{signal.leverage}倍**", "inline": True},
                {"name": "💪 信号强度", "value": signal.confidence, "inline": True},
                {"name": "📝 策略说明", "value": signal.description, "inline": False}
            ],
            "footer": {"text": f"⚠️ 风险提示: 仅供参考 | {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"}
        }

        try:
            response = requests.post(
                self.discord_webhook,
                json={"embeds": [embed]},
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"Discord发送失败: {e}")
            return False

    def send_startup_message(self):
        """发送启动消息"""
        # Telegram
        try:
            tg_msg = """🤖 <b>BTC交易信号监控已启动</b>

📊 <b>监控策略:</b>
• EMA 交叉 (7/25, 50/200)
• RSI 极端值
• MACD 交叉
• 恐惧贪婪指数
• Pin Bar 形态
• 成交量突破
• 闪崩检测

⏰ <b>检查频率:</b> 每分钟
📈 <b>数据源:</b> 币安公共API

<i>Bot正在运行中...</i>"""

            url = f"https://api.telegram.org/bot{self.tg_token}/sendMessage"
            requests.post(url, json={"chat_id": self.tg_chat_id, "text": tg_msg, "parse_mode": "HTML"}, timeout=10)
        except:
            pass

        # Discord
        try:
            embed = {
                "title": "🤖 BTC交易信号监控已启动",
                "color": 0x00BFFF,
                "fields": [
                    {"name": "📊 监控策略", "value": "• EMA交叉\n• RSI极端值\n• MACD交叉\n• 恐惧贪婪指数\n• Pin Bar形态\n• 成交量突破", "inline": False},
                    {"name": "⏰ 检查频率", "value": "每分钟", "inline": True},
                    {"name": "📈 数据源", "value": "币安API", "inline": True}
                ],
                "footer": {"text": "Bot正在运行中..."}
            }
            requests.post(self.discord_webhook, json={"embeds": [embed]}, timeout=10)
        except:
            pass


def print_banner():
    """打印启动横幅"""
    banner = """
╔══════════════════════════════════════════════════════════╗
║                                                          ║
║     BTC/USDT 实时交易信号监控器 v1.0                      ║
║                                                          ║
║     • 实时监控币安K线数据                                 ║
║     • 自动检测多种交易信号                                ║
║     • 同步推送到 Telegram & Discord                       ║
║                                                          ║
╚══════════════════════════════════════════════════════════╝
"""
    print(banner)


def main():
    """主函数"""
    print_banner()

    # 初始化
    detector = SignalDetector()
    sender = NotificationSender()

    print(f"[{datetime.datetime.now()}] 正在启动监控...")
    print(f"[{datetime.datetime.now()}] 检查间隔: {CHECK_INTERVAL}秒")
    print(f"[{datetime.datetime.now()}] Telegram Chat ID: {TELEGRAM_CHAT_ID}")
    print(f"[{datetime.datetime.now()}] Discord Webhook: {DISCORD_WEBHOOK_URL[:50]}...")
    print()

    # 发送启动消息
    sender.send_startup_message()
    print(f"[{datetime.datetime.now()}] ✅ 启动消息已发送")
    print()

    # 主循环
    while True:
        try:
            # 获取数据
            klines = BinanceAPI.get_klines("BTCUSDT", "1h", 200)
            fear_greed = FearGreedAPI.get_index()

            if not klines:
                print(f"[{datetime.datetime.now()}] ⚠️ 无法获取K线数据，跳过...")
                time.sleep(CHECK_INTERVAL)
                continue

            current_price = klines[-1]["close"]

            # 检测信号
            signals = detector.detect_signals(klines, fear_greed)

            # 发送信号
            for signal in signals:
                print(f"[{datetime.datetime.now()}] 🚨 发现信号: {signal.strategy_name} - {signal.signal_type.value}")
                if sender.send_signal(signal):
                    print(f"[{datetime.datetime.now()}] ✅ 信号已推送")
                else:
                    print(f"[{datetime.datetime.now()}] ❌ 信号推送失败")

            # 状态输出
            fg_str = f"F&G={fear_greed}" if fear_greed else "F&G=N/A"
            print(f"[{datetime.datetime.now()}] BTC=${current_price:,.2f} | {fg_str} | 检测到{len(signals)}个信号")

        except KeyboardInterrupt:
            print(f"\n[{datetime.datetime.now()}] 👋 监控已停止")
            break
        except Exception as e:
            print(f"[{datetime.datetime.now()}] ❌ 错误: {e}")

        time.sleep(CHECK_INTERVAL)


if __name__ == "__main__":
    main()
