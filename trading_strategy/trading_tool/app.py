#!/usr/bin/env python3
"""
BTC/USDT 自动交易工具
- 支持AI全自动交易和手动交易模式
- 实时查看交易状态和收益
- 移动止盈止损
"""

import os
import json
import time
import threading
from datetime import datetime
from flask import Flask, render_template, request, jsonify
import pandas as pd

from binance_api import BinanceAPI, test_connection
from strategies import (
    get_all_strategies, get_triggered_strategies, get_fear_greed_index,
    calculate_indicators, HIGH_WIN_RATE_STRATEGIES
)

app = Flask(__name__)

# 全局状态
class TradingState:
    def __init__(self):
        self.api = None
        self.api_key = ""
        self.api_secret = ""
        self.testnet = True
        self.connected = False

        # 交易模式
        self.mode = "manual"  # auto / manual
        self.auto_running = False

        # 当前持仓
        self.position = None
        self.position_strategy = None

        # 交易历史
        self.trades = []

        # 监控线程
        self.monitor_thread = None
        self.stop_flag = False

        # 设置
        self.auto_strategies = []  # 自动模式使用的策略
        self.check_interval = 60  # 检查间隔(秒)
        self.max_position_usdt = 100  # 最大仓位USDT

        # 移动止损状态
        self.trailing_stop = {
            'enabled': True,
            'trail_pct': 5,
            'highest_price': 0,
            'current_sl': 0
        }

state = TradingState()


@app.route('/')
def index():
    """主页"""
    return render_template('index.html')


@app.route('/api/connect', methods=['POST'])
def connect():
    """连接币安API"""
    data = request.json
    state.api_key = data.get('api_key', '')
    state.api_secret = data.get('api_secret', '')
    state.testnet = data.get('testnet', True)

    result = test_connection(state.api_key, state.api_secret, state.testnet)

    if result['success']:
        state.api = BinanceAPI(state.api_key, state.api_secret, state.testnet)
        state.connected = True
        return jsonify({
            'success': True,
            'message': '连接成功' + (' (测试网)' if state.testnet else ' (主网)'),
            'balance': result['balance'],
            'price': result['price']
        })
    else:
        return jsonify({
            'success': False,
            'message': result['error']
        })


@app.route('/api/disconnect', methods=['POST'])
def disconnect():
    """断开连接"""
    state.api = None
    state.connected = False
    state.auto_running = False
    state.stop_flag = True
    return jsonify({'success': True})


@app.route('/api/status')
def get_status():
    """获取当前状态"""
    data = {
        'connected': state.connected,
        'mode': state.mode,
        'auto_running': state.auto_running,
        'testnet': state.testnet
    }

    if state.connected and state.api:
        # 获取账户信息
        balance = state.api.get_balance('USDT')
        position = state.api.get_position('BTCUSDT')
        price_data = state.api.futures_ticker_price('BTCUSDT')

        data['balance'] = balance
        data['position'] = position
        data['price'] = float(price_data.get('price', 0)) if isinstance(price_data, dict) else 0

        # 恐惧贪婪指数
        fear_value, fear_class = get_fear_greed_index()
        data['fear_index'] = fear_value
        data['fear_class'] = fear_class

        # 移动止损状态
        if position and state.trailing_stop['enabled']:
            data['trailing_stop'] = {
                'highest_price': state.trailing_stop['highest_price'],
                'current_sl': state.trailing_stop['current_sl'],
                'trail_pct': state.trailing_stop['trail_pct']
            }

    return jsonify(data)


@app.route('/api/strategies')
def get_strategies():
    """获取所有策略"""
    strategies = get_all_strategies()
    # 按胜率排序
    strategies.sort(key=lambda x: x['win_rate'], reverse=True)
    return jsonify(strategies)


@app.route('/api/check_signals')
def check_signals():
    """检查当前信号"""
    if not state.connected:
        return jsonify({'error': '未连接'})

    timeframe = request.args.get('timeframe', '1h')

    # 获取K线数据
    interval_map = {'1h': '1h', '4h': '4h', '1d': '1d', '1w': '1w'}
    interval = interval_map.get(timeframe, '1h')

    klines = state.api.futures_klines('BTCUSDT', interval, limit=300)
    if 'error' in klines if isinstance(klines, dict) else False:
        return jsonify({'error': str(klines)})

    # 转换为DataFrame
    df = pd.DataFrame(klines, columns=[
        'timestamp', 'open', 'high', 'low', 'close', 'volume',
        'close_time', 'quote_volume', 'trades', 'taker_buy_base',
        'taker_buy_quote', 'ignore'
    ])
    df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
    for col in ['open', 'high', 'low', 'close', 'volume']:
        df[col] = df[col].astype(float)

    # 获取恐惧指数
    fear_value, _ = get_fear_greed_index()

    # 检查信号
    triggered = get_triggered_strategies(df, fear_value, timeframe)

    return jsonify({
        'timeframe': timeframe,
        'triggered': triggered,
        'fear_index': fear_value,
        'current_price': float(df.iloc[-1]['close']),
        'checked_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    })


@app.route('/api/open_position', methods=['POST'])
def open_position():
    """手动开仓"""
    if not state.connected:
        return jsonify({'success': False, 'error': '未连接'})

    # 检查是否已有持仓
    position = state.api.get_position('BTCUSDT')
    if position:
        return jsonify({'success': False, 'error': '已有持仓，请先平仓'})

    data = request.json
    strategy_name = data.get('strategy', '')
    tp_pct = float(data.get('tp_pct', 100))
    sl_pct = float(data.get('sl_pct', 5))
    trail_pct = float(data.get('trail_pct', 5))
    leverage = int(data.get('leverage', 10))
    amount_usdt = float(data.get('amount_usdt', 100))

    # 获取当前价格
    price_data = state.api.futures_ticker_price('BTCUSDT')
    current_price = float(price_data['price'])

    # 计算数量
    quantity = round(amount_usdt * leverage / current_price, 3)

    # 计算止盈止损价格
    tp_price = round(current_price * (1 + tp_pct / 100), 2)
    sl_price = round(current_price * (1 - sl_pct / 100), 2)

    # 开仓
    result = state.api.open_long(
        symbol='BTCUSDT',
        quantity=quantity,
        leverage=leverage,
        tp_price=tp_price,
        sl_price=sl_price
    )

    if result['success']:
        # 更新状态
        state.position_strategy = strategy_name
        state.trailing_stop = {
            'enabled': trail_pct > 0,
            'trail_pct': trail_pct,
            'highest_price': current_price,
            'current_sl': sl_price
        }

        # 记录交易
        trade = {
            'id': len(state.trades) + 1,
            'strategy': strategy_name,
            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entry_price': current_price,
            'quantity': quantity,
            'leverage': leverage,
            'tp_pct': tp_pct,
            'sl_pct': sl_pct,
            'trail_pct': trail_pct,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'status': 'open'
        }
        state.trades.append(trade)

        return jsonify({
            'success': True,
            'message': f'开仓成功: {quantity} BTC @ ${current_price}',
            'orders': result['orders'],
            'trade': trade
        })
    else:
        return jsonify({'success': False, 'error': result.get('error', '开仓失败')})


@app.route('/api/close_position', methods=['POST'])
def close_position():
    """平仓"""
    if not state.connected:
        return jsonify({'success': False, 'error': '未连接'})

    position = state.api.get_position('BTCUSDT')
    if not position:
        return jsonify({'success': False, 'error': '没有持仓'})

    # 取消所有挂单
    state.api.futures_cancel_all_orders('BTCUSDT')

    # 市价平仓
    result = state.api.close_long('BTCUSDT')

    if 'error' not in result:
        # 更新交易记录
        if state.trades and state.trades[-1]['status'] == 'open':
            price_data = state.api.futures_ticker_price('BTCUSDT')
            exit_price = float(price_data['price'])

            state.trades[-1]['exit_time'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            state.trades[-1]['exit_price'] = exit_price
            state.trades[-1]['pnl_pct'] = (exit_price - state.trades[-1]['entry_price']) / state.trades[-1]['entry_price'] * 100
            state.trades[-1]['status'] = 'closed'

        state.position_strategy = None
        state.trailing_stop['highest_price'] = 0
        state.trailing_stop['current_sl'] = 0

        return jsonify({'success': True, 'message': '平仓成功', 'order': result})
    else:
        return jsonify({'success': False, 'error': result['error']})


@app.route('/api/trades')
def get_trades():
    """获取交易历史"""
    return jsonify(state.trades)


@app.route('/api/set_mode', methods=['POST'])
def set_mode():
    """设置交易模式"""
    data = request.json
    state.mode = data.get('mode', 'manual')

    if state.mode == 'auto':
        state.auto_strategies = data.get('strategies', [])
        state.check_interval = int(data.get('interval', 60))
        state.max_position_usdt = float(data.get('max_position', 100))
    else:
        state.auto_running = False
        state.stop_flag = True

    return jsonify({
        'success': True,
        'mode': state.mode,
        'auto_strategies': state.auto_strategies
    })


@app.route('/api/start_auto', methods=['POST'])
def start_auto():
    """启动自动交易"""
    if not state.connected:
        return jsonify({'success': False, 'error': '未连接'})

    if state.mode != 'auto':
        return jsonify({'success': False, 'error': '请先切换到自动模式'})

    if state.auto_running:
        return jsonify({'success': False, 'error': '自动交易已在运行'})

    state.auto_running = True
    state.stop_flag = False

    # 启动监控线程
    def auto_trade_loop():
        while not state.stop_flag and state.auto_running:
            try:
                auto_trade_check()
            except Exception as e:
                print(f"自动交易错误: {e}")
            time.sleep(state.check_interval)

    state.monitor_thread = threading.Thread(target=auto_trade_loop, daemon=True)
    state.monitor_thread.start()

    return jsonify({'success': True, 'message': '自动交易已启动'})


@app.route('/api/stop_auto', methods=['POST'])
def stop_auto():
    """停止自动交易"""
    state.auto_running = False
    state.stop_flag = True
    return jsonify({'success': True, 'message': '自动交易已停止'})


def auto_trade_check():
    """自动交易检查"""
    if not state.connected or not state.api:
        return

    # 检查是否已有持仓
    position = state.api.get_position('BTCUSDT')

    if position:
        # 已有持仓，检查移动止损
        update_trailing_stop(position)
    else:
        # 没有持仓，检查信号
        check_and_open_position()


def update_trailing_stop(position):
    """更新移动止损"""
    if not state.trailing_stop['enabled']:
        return

    current_price = position['entry_price'] + position['unrealized_pnl'] / position['quantity']

    # 更新最高价
    if current_price > state.trailing_stop['highest_price']:
        state.trailing_stop['highest_price'] = current_price

        # 计算新的移动止损价
        new_sl = state.trailing_stop['highest_price'] * (1 - state.trailing_stop['trail_pct'] / 100)

        # 只有新止损高于当前止损才更新
        if new_sl > state.trailing_stop['current_sl']:
            state.trailing_stop['current_sl'] = new_sl

            # 更新止损单
            state.api.futures_cancel_all_orders('BTCUSDT')
            state.api.futures_new_order(
                symbol='BTCUSDT',
                side='SELL',
                order_type='STOP_MARKET',
                stop_price=round(new_sl, 2),
                close_position=True
            )


def check_and_open_position():
    """检查信号并开仓"""
    # 检查所有选中的策略周期
    timeframes = set(s['timeframe'] for s in state.auto_strategies)

    fear_value, _ = get_fear_greed_index()

    for tf in timeframes:
        # 获取K线
        klines = state.api.futures_klines('BTCUSDT', tf, limit=300)
        if isinstance(klines, dict) and 'error' in klines:
            continue

        df = pd.DataFrame(klines, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'quote_volume', 'trades', 'taker_buy_base',
            'taker_buy_quote', 'ignore'
        ])
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)

        # 检查信号
        triggered = get_triggered_strategies(df, fear_value, tf)

        # 检查是否有选中的策略触发
        for strategy in triggered:
            for selected in state.auto_strategies:
                if strategy['name'] == selected['name'] and strategy['timeframe'] == selected['timeframe']:
                    # 触发开仓
                    execute_auto_open(strategy, float(df.iloc[-1]['close']))
                    return


def execute_auto_open(strategy, current_price):
    """执行自动开仓"""
    tp_pct = strategy['tp']
    sl_pct = strategy['sl']
    trail_pct = strategy['trail']
    leverage = strategy['leverage']

    quantity = round(state.max_position_usdt * leverage / current_price, 3)
    tp_price = round(current_price * (1 + tp_pct / 100), 2)
    sl_price = round(current_price * (1 - sl_pct / 100), 2)

    result = state.api.open_long(
        symbol='BTCUSDT',
        quantity=quantity,
        leverage=leverage,
        tp_price=tp_price,
        sl_price=sl_price
    )

    if result['success']:
        state.position_strategy = strategy['name']
        state.trailing_stop = {
            'enabled': trail_pct > 0,
            'trail_pct': trail_pct,
            'highest_price': current_price,
            'current_sl': sl_price
        }

        trade = {
            'id': len(state.trades) + 1,
            'strategy': strategy['name'],
            'timeframe': strategy['timeframe'],
            'entry_time': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'entry_price': current_price,
            'quantity': quantity,
            'leverage': leverage,
            'tp_pct': tp_pct,
            'sl_pct': sl_pct,
            'trail_pct': trail_pct,
            'tp_price': tp_price,
            'sl_price': sl_price,
            'status': 'open',
            'auto': True
        }
        state.trades.append(trade)


@app.route('/api/update_trailing', methods=['POST'])
def update_trailing():
    """手动更新移动止损设置"""
    data = request.json
    state.trailing_stop['enabled'] = data.get('enabled', True)
    state.trailing_stop['trail_pct'] = float(data.get('trail_pct', 5))
    return jsonify({'success': True, 'trailing_stop': state.trailing_stop})


if __name__ == '__main__':
    print("=" * 60)
    print("BTC/USDT 自动交易工具")
    print("=" * 60)
    print("请在浏览器中打开: http://localhost:5000")
    print("=" * 60)
    app.run(host='0.0.0.0', port=5000, debug=True, threaded=True)
