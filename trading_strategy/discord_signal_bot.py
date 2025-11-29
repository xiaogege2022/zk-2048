#!/usr/bin/env python3
"""
BTC/USDT Trading Signal Discord Bot
基于策略分析报告生成交易信号并推送到Discord频道
"""

import requests
import time
import datetime
import json
from dataclasses import dataclass
from typing import Optional, List
from enum import Enum

# ============================================
# 配置区域 - Discord Webhook URL
# ============================================
DISCORD_WEBHOOK_URL = "https://discord.com/api/webhooks/1444323268600266773/i5WXa-v66RrHnl6SP6IVXw4vtABzavxxeOZo6OJAk_gRMV-Khx88wWRSE_aNQ4kSqtEm"

# ============================================
# 策略配置
# ============================================

class SignalType(Enum):
    LONG = "LONG"
    SHORT = "SHORT"

@dataclass
class TradingSignal:
    signal_type: SignalType
    strategy_name: str
    win_rate: float
    entry_price: float
    take_profit: float
    stop_loss: float
    leverage: int
    confidence: str
    description: str

# 策略配置 - 基于报告中的最佳策略
STRATEGIES = {
    "EMA_7_25_Cross": {
        "win_rate": 80.0,
        "tp_pct": 15.0,
        "sl_pct": 7.0,
        "leverage": 25,
        "description": "EMA7上穿EMA25金叉信号"
    },
    "Breakout_Buy": {
        "win_rate": 78.1,
        "tp_pct": 12.0,
        "sl_pct": 6.0,
        "leverage": 30,
        "description": "7天盘整后突破买入"
    },
    "Flash_Crash_Bottom": {
        "win_rate": 66.7,
        "tp_pct": 20.0,
        "sl_pct": 10.0,
        "leverage": 20,
        "description": "闪崩底部抄底信号"
    },
    "Bullish_Pin_Bar": {
        "win_rate": 71.4,
        "tp_pct": 15.0,
        "sl_pct": 8.0,
        "leverage": 25,
        "description": "看涨Pin Bar形态"
    },
    "EMA_50_200_Cross": {
        "win_rate": 71.4,
        "tp_pct": 25.0,
        "sl_pct": 10.0,
        "leverage": 35,
        "description": "EMA50上穿EMA200黄金交叉"
    },
    "RSI_Extreme_Oversold": {
        "win_rate": 78.0,
        "tp_pct": 15.0,
        "sl_pct": 7.0,
        "leverage": 20,
        "description": "RSI极度超卖(<20)反弹"
    },
    "Fear_Extreme": {
        "win_rate": 78.0,
        "tp_pct": 20.0,
        "sl_pct": 10.0,
        "leverage": 25,
        "description": "恐惧贪婪指数<10极度恐惧"
    },
    "Death_Cross": {
        "win_rate": 68.0,
        "tp_pct": 15.0,
        "sl_pct": 7.0,
        "leverage": 20,
        "description": "EMA50下穿EMA200死亡交叉",
        "is_short": True
    },
    "RSI_Extreme_Overbought": {
        "win_rate": 72.0,
        "tp_pct": 10.0,
        "sl_pct": 5.0,
        "leverage": 15,
        "description": "RSI极度超买(>80)回调",
        "is_short": True
    }
}


class DiscordSignalBot:
    def __init__(self, webhook_url: str):
        self.webhook_url = webhook_url

    def send_message(self, content: str = None, embed: dict = None) -> bool:
        """发送消息到Discord频道"""
        payload = {}
        if content:
            payload["content"] = content
        if embed:
            payload["embeds"] = [embed]

        try:
            response = requests.post(
                self.webhook_url,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=10
            )
            return response.status_code in [200, 204]
        except Exception as e:
            print(f"发送消息失败: {e}")
            return False

    def format_signal_embed(self, signal: TradingSignal) -> dict:
        """格式化交易信号为Discord Embed"""
        now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        # 计算止盈止损价格
        if signal.signal_type == SignalType.LONG:
            tp_price = signal.entry_price * (1 + signal.take_profit / 100)
            sl_price = signal.entry_price * (1 - signal.stop_loss / 100)
            color = 0x00FF00  # 绿色
            direction_emoji = "🟢"
            direction_text = "做多 LONG"
        else:
            tp_price = signal.entry_price * (1 - signal.take_profit / 100)
            sl_price = signal.entry_price * (1 + signal.stop_loss / 100)
            color = 0xFF0000  # 红色
            direction_emoji = "🔴"
            direction_text = "做空 SHORT"

        embed = {
            "title": "🚨 BTC/USDT 交易信号",
            "color": color,
            "fields": [
                {"name": "📊 方向", "value": f"{direction_emoji} **{direction_text}**", "inline": True},
                {"name": "📈 策略", "value": signal.strategy_name, "inline": True},
                {"name": "🎯 胜率", "value": f"**{signal.win_rate:.1f}%**", "inline": True},
                {"name": "💰 入场价格", "value": f"${signal.entry_price:,.2f}", "inline": True},
                {"name": "✅ 止盈", "value": f"${tp_price:,.2f} (+{signal.take_profit:.1f}%)", "inline": True},
                {"name": "❌ 止损", "value": f"${sl_price:,.2f} (-{signal.stop_loss:.1f}%)", "inline": True},
                {"name": "⚡ 杠杆倍数", "value": f"**{signal.leverage}倍**", "inline": True},
                {"name": "💪 信号强度", "value": signal.confidence, "inline": True},
                {"name": "📝 策略说明", "value": signal.description, "inline": False}
            ],
            "footer": {"text": f"⚠️ 风险提示: 仅供参考，请自行判断 | {now}"}
        }
        return embed

    def send_signal(self, signal: TradingSignal) -> bool:
        """发送交易信号"""
        embed = self.format_signal_embed(signal)
        return self.send_message(embed=embed)

    def test_connection(self) -> bool:
        """测试Discord连接"""
        test_embed = {
            "title": "✅ 连接测试成功",
            "description": "Discord Webhook 配置正确！",
            "color": 0x00FF00
        }
        return self.send_message(embed=test_embed)


class MarketDataFetcher:
    """获取实时市场数据"""

    @staticmethod
    def get_btc_price() -> Optional[float]:
        """获取BTC当前价格"""
        try:
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return float(response.json()["price"])
        except:
            pass

        try:
            url = "https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return response.json()["bitcoin"]["usd"]
        except:
            pass

        return None

    @staticmethod
    def get_fear_greed_index() -> Optional[int]:
        """获取恐惧贪婪指数"""
        try:
            url = "https://api.alternative.me/fng/"
            response = requests.get(url, timeout=10)
            if response.status_code == 200:
                return int(response.json()["data"][0]["value"])
        except:
            pass
        return None


class SignalGenerator:
    """信号生成器 - 基于策略报告"""

    def __init__(self):
        self.ema_7 = []
        self.ema_25 = []
        self.ema_50 = []
        self.ema_99 = []
        self.ema_200 = []
        self.prices = []
        self.rsi_values = []

    def update_price(self, price: float):
        """更新价格数据"""
        self.prices.append(price)
        if len(self.prices) > 200:
            self.prices = self.prices[-200:]

        self.ema_7 = self._calculate_ema(7)
        self.ema_25 = self._calculate_ema(25)
        self.ema_50 = self._calculate_ema(50)
        self.ema_99 = self._calculate_ema(99)
        self.ema_200 = self._calculate_ema(200)
        self.rsi_values = self._calculate_rsi(14)

    def _calculate_ema(self, period: int) -> List[float]:
        """计算EMA"""
        if len(self.prices) < period:
            return []

        ema = []
        multiplier = 2 / (period + 1)
        sma = sum(self.prices[:period]) / period
        ema.append(sma)

        for i in range(period, len(self.prices)):
            new_ema = (self.prices[i] - ema[-1]) * multiplier + ema[-1]
            ema.append(new_ema)

        return ema

    def _calculate_rsi(self, period: int = 14) -> List[float]:
        """计算RSI"""
        if len(self.prices) < period + 1:
            return []

        rsi = []
        gains = []
        losses = []

        for i in range(1, len(self.prices)):
            change = self.prices[i] - self.prices[i-1]
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

    def check_signals(self, current_price: float, fear_greed: Optional[int] = None) -> List[TradingSignal]:
        """检查是否有交易信号"""
        signals = []

        if len(self.prices) < 50:
            return signals

        # 1. EMA 7/25 交叉
        if len(self.ema_7) >= 2 and len(self.ema_25) >= 2:
            if self.ema_7[-2] <= self.ema_25[-2] and self.ema_7[-1] > self.ema_25[-1]:
                config = STRATEGIES["EMA_7_25_Cross"]
                signals.append(TradingSignal(
                    signal_type=SignalType.LONG,
                    strategy_name="EMA 7/25 金叉",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐⭐ 强",
                    description=config["description"]
                ))

            if self.ema_7[-2] >= self.ema_25[-2] and self.ema_7[-1] < self.ema_25[-1]:
                signals.append(TradingSignal(
                    signal_type=SignalType.SHORT,
                    strategy_name="EMA 7/25 死叉",
                    win_rate=65.0,
                    entry_price=current_price,
                    take_profit=10.0,
                    stop_loss=5.0,
                    leverage=20,
                    confidence="⭐⭐⭐⭐ 中强",
                    description="EMA7下穿EMA25死叉信号"
                ))

        # 2. EMA 50/200 交叉
        if len(self.ema_50) >= 2 and len(self.ema_200) >= 2:
            if self.ema_50[-2] <= self.ema_200[-2] and self.ema_50[-1] > self.ema_200[-1]:
                config = STRATEGIES["EMA_50_200_Cross"]
                signals.append(TradingSignal(
                    signal_type=SignalType.LONG,
                    strategy_name="黄金交叉",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐⭐ 强",
                    description=config["description"]
                ))

            if self.ema_50[-2] >= self.ema_200[-2] and self.ema_50[-1] < self.ema_200[-1]:
                config = STRATEGIES["Death_Cross"]
                signals.append(TradingSignal(
                    signal_type=SignalType.SHORT,
                    strategy_name="死亡交叉",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐⭐ 强",
                    description=config["description"]
                ))

        # 3. RSI 极端信号
        if self.rsi_values:
            current_rsi = self.rsi_values[-1]

            if current_rsi < 20:
                config = STRATEGIES["RSI_Extreme_Oversold"]
                signals.append(TradingSignal(
                    signal_type=SignalType.LONG,
                    strategy_name=f"RSI极度超卖 ({current_rsi:.1f})",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐⭐ 强",
                    description=config["description"]
                ))

            elif current_rsi > 80:
                config = STRATEGIES["RSI_Extreme_Overbought"]
                signals.append(TradingSignal(
                    signal_type=SignalType.SHORT,
                    strategy_name=f"RSI极度超买 ({current_rsi:.1f})",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐ 中强",
                    description=config["description"]
                ))

        # 4. 恐惧贪婪指数
        if fear_greed is not None:
            if fear_greed <= 10:
                config = STRATEGIES["Fear_Extreme"]
                signals.append(TradingSignal(
                    signal_type=SignalType.LONG,
                    strategy_name=f"极度恐惧 (F&G={fear_greed})",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐⭐ 强",
                    description=config["description"]
                ))

        # 5. 闪崩检测
        if len(self.prices) >= 7:
            price_7d_ago = self.prices[-7]
            change_7d = (current_price - price_7d_ago) / price_7d_ago * 100

            if change_7d <= -15:
                config = STRATEGIES["Flash_Crash_Bottom"]
                signals.append(TradingSignal(
                    signal_type=SignalType.LONG,
                    strategy_name=f"7日暴跌 ({change_7d:.1f}%)",
                    win_rate=config["win_rate"],
                    entry_price=current_price,
                    take_profit=config["tp_pct"],
                    stop_loss=config["sl_pct"],
                    leverage=config["leverage"],
                    confidence="⭐⭐⭐⭐ 中强",
                    description=config["description"]
                ))

        return signals


def main():
    """主函数"""
    print("=" * 50)
    print("BTC/USDT 交易信号 Discord Bot")
    print("=" * 50)

    # 初始化
    bot = DiscordSignalBot(DISCORD_WEBHOOK_URL)
    data_fetcher = MarketDataFetcher()
    signal_generator = SignalGenerator()

    # 测试连接
    print("\n正在测试 Discord 连接...")
    if not bot.test_connection():
        print("❌ 无法连接到 Discord，请检查 Webhook URL")
        return

    print("✅ Discord 连接成功！")

    # 发送启动消息
    startup_embed = {
        "title": "🤖 BTC信号Bot已启动",
        "color": 0x00BFFF,
        "fields": [
            {
                "name": "📊 监控策略",
                "value": "• EMA 7/25 交叉\n• EMA 50/200 黄金/死亡交叉\n• RSI 极端值\n• 恐惧贪婪指数\n• 闪崩检测",
                "inline": False
            },
            {
                "name": "⏰ 检查频率",
                "value": "每5分钟",
                "inline": True
            },
            {
                "name": "📈 数据源",
                "value": "Binance",
                "inline": True
            }
        ],
        "footer": {
            "text": "Bot正在运行中..."
        }
    }
    bot.send_message(embed=startup_embed)
    print("\n✅ Bot已启动，开始监控...")

    # 主循环
    check_interval = 300  # 5分钟
    last_signals = set()

    while True:
        try:
            current_price = data_fetcher.get_btc_price()
            if current_price is None:
                print(f"[{datetime.datetime.now()}] 无法获取价格，跳过...")
                time.sleep(60)
                continue

            fear_greed = data_fetcher.get_fear_greed_index()
            signal_generator.update_price(current_price)
            signals = signal_generator.check_signals(current_price, fear_greed)

            for signal in signals:
                signal_key = f"{signal.strategy_name}_{signal.signal_type.value}"
                if signal_key not in last_signals:
                    print(f"[{datetime.datetime.now()}] 发送信号: {signal.strategy_name}")
                    bot.send_signal(signal)
                    last_signals.add(signal_key)

            if datetime.datetime.now().minute == 0:
                last_signals.clear()

            print(f"[{datetime.datetime.now()}] BTC=${current_price:,.2f} | F&G={fear_greed} | 信号数={len(signals)}")

        except KeyboardInterrupt:
            print("\n\n👋 Bot已停止")
            stop_embed = {
                "title": "🔴 BTC信号Bot已停止",
                "color": 0xFF0000
            }
            bot.send_message(embed=stop_embed)
            break
        except Exception as e:
            print(f"错误: {e}")

        time.sleep(check_interval)


def send_test_signal():
    """发送测试信号"""
    bot = DiscordSignalBot(DISCORD_WEBHOOK_URL)

    price = MarketDataFetcher.get_btc_price() or 95000

    test_signal = TradingSignal(
        signal_type=SignalType.LONG,
        strategy_name="测试信号 - EMA金叉",
        win_rate=80.0,
        entry_price=price,
        take_profit=15.0,
        stop_loss=7.0,
        leverage=25,
        confidence="⭐⭐⭐⭐⭐ 强",
        description="这是一条测试信号，用于验证Bot是否正常工作"
    )

    if bot.send_signal(test_signal):
        print("✅ 测试信号发送成功！请检查 Discord 频道")
    else:
        print("❌ 测试信号发送失败")


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "test":
        send_test_signal()
    else:
        main()
