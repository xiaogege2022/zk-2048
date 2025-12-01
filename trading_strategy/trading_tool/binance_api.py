#!/usr/bin/env python3
"""
币安API交易接口
支持现货和合约交易
"""

import hmac
import hashlib
import time
import requests
from urllib.parse import urlencode
from typing import Optional, Dict, Any


class BinanceAPI:
    """币安API封装类"""

    # API端点
    SPOT_BASE_URL = "https://api.binance.com"
    FUTURES_BASE_URL = "https://fapi.binance.com"

    def __init__(self, api_key: str = "", api_secret: str = "", testnet: bool = False):
        """
        初始化API

        参数:
            api_key: API密钥
            api_secret: API密钥
            testnet: 是否使用测试网
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.testnet = testnet

        if testnet:
            self.FUTURES_BASE_URL = "https://testnet.binancefuture.com"

        self.session = requests.Session()
        self.session.headers.update({
            'X-MBX-APIKEY': api_key
        })

    def _sign(self, params: Dict[str, Any]) -> str:
        """生成签名"""
        query_string = urlencode(params)
        signature = hmac.new(
            self.api_secret.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        return signature

    def _request(self, method: str, url: str, params: Dict = None, signed: bool = False) -> Dict:
        """发送请求"""
        params = params or {}

        if signed:
            params['timestamp'] = int(time.time() * 1000)
            params['signature'] = self._sign(params)

        try:
            if method == 'GET':
                response = self.session.get(url, params=params, timeout=10)
            elif method == 'POST':
                response = self.session.post(url, params=params, timeout=10)
            elif method == 'DELETE':
                response = self.session.delete(url, params=params, timeout=10)
            else:
                raise ValueError(f"Unknown method: {method}")

            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            return {'error': str(e)}

    # ==================== 合约API ====================

    def futures_account_balance(self) -> Dict:
        """获取合约账户余额"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v2/balance"
        return self._request('GET', url, signed=True)

    def futures_account_info(self) -> Dict:
        """获取合约账户信息"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v2/account"
        return self._request('GET', url, signed=True)

    def futures_position_info(self, symbol: str = None) -> Dict:
        """获取持仓信息"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v2/positionRisk"
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', url, params, signed=True)

    def futures_klines(self, symbol: str, interval: str, limit: int = 500) -> list:
        """获取K线数据"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/klines"
        params = {
            'symbol': symbol,
            'interval': interval,
            'limit': limit
        }
        return self._request('GET', url, params)

    def futures_ticker_price(self, symbol: str = None) -> Dict:
        """获取最新价格"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/ticker/price"
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', url, params)

    def futures_set_leverage(self, symbol: str, leverage: int) -> Dict:
        """设置杠杆倍数"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/leverage"
        params = {
            'symbol': symbol,
            'leverage': leverage
        }
        return self._request('POST', url, params, signed=True)

    def futures_set_margin_type(self, symbol: str, margin_type: str = 'ISOLATED') -> Dict:
        """设置保证金模式 (ISOLATED/CROSSED)"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/marginType"
        params = {
            'symbol': symbol,
            'marginType': margin_type
        }
        return self._request('POST', url, params, signed=True)

    def futures_new_order(self, symbol: str, side: str, order_type: str,
                          quantity: float = None, price: float = None,
                          stop_price: float = None, close_position: bool = False,
                          reduce_only: bool = False, time_in_force: str = None,
                          position_side: str = 'BOTH') -> Dict:
        """
        下单

        参数:
            symbol: 交易对 (如 BTCUSDT)
            side: BUY/SELL
            order_type: LIMIT/MARKET/STOP_MARKET/TAKE_PROFIT_MARKET
            quantity: 数量
            price: 价格 (LIMIT订单需要)
            stop_price: 触发价格 (STOP订单需要)
            close_position: 是否全部平仓
            reduce_only: 是否只减仓
            time_in_force: GTC/IOC/FOK
            position_side: BOTH/LONG/SHORT (双向持仓模式)
        """
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/order"
        params = {
            'symbol': symbol,
            'side': side,
            'type': order_type,
            'positionSide': position_side
        }

        if quantity:
            params['quantity'] = quantity
        if price:
            params['price'] = price
        if stop_price:
            params['stopPrice'] = stop_price
        if close_position:
            params['closePosition'] = 'true'
        if reduce_only:
            params['reduceOnly'] = 'true'
        if time_in_force:
            params['timeInForce'] = time_in_force

        return self._request('POST', url, params, signed=True)

    def futures_cancel_order(self, symbol: str, order_id: int = None) -> Dict:
        """取消订单"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/order"
        params = {'symbol': symbol}
        if order_id:
            params['orderId'] = order_id
        return self._request('DELETE', url, params, signed=True)

    def futures_cancel_all_orders(self, symbol: str) -> Dict:
        """取消所有订单"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/allOpenOrders"
        params = {'symbol': symbol}
        return self._request('DELETE', url, params, signed=True)

    def futures_open_orders(self, symbol: str = None) -> Dict:
        """查询当前挂单"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/openOrders"
        params = {}
        if symbol:
            params['symbol'] = symbol
        return self._request('GET', url, params, signed=True)

    def futures_all_orders(self, symbol: str, limit: int = 50) -> Dict:
        """查询所有订单"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/allOrders"
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self._request('GET', url, params, signed=True)

    def futures_user_trades(self, symbol: str, limit: int = 50) -> Dict:
        """查询成交历史"""
        url = f"{self.FUTURES_BASE_URL}/fapi/v1/userTrades"
        params = {
            'symbol': symbol,
            'limit': limit
        }
        return self._request('GET', url, params, signed=True)

    # ==================== 便捷方法 ====================

    def open_long(self, symbol: str, quantity: float, leverage: int = 10,
                  tp_price: float = None, sl_price: float = None) -> Dict:
        """
        开多仓

        参数:
            symbol: 交易对
            quantity: 数量
            leverage: 杠杆倍数
            tp_price: 止盈价格
            sl_price: 止损价格

        返回:
            {'success': bool, 'order': {}, 'tp_order': {}, 'sl_order': {}, 'error': str}
        """
        result = {'success': False, 'orders': []}

        # 设置杠杆
        lev_result = self.futures_set_leverage(symbol, leverage)
        if 'error' in lev_result:
            result['error'] = f"设置杠杆失败: {lev_result['error']}"
            return result

        # 开仓
        order = self.futures_new_order(
            symbol=symbol,
            side='BUY',
            order_type='MARKET',
            quantity=quantity
        )

        if 'error' in order:
            result['error'] = f"开仓失败: {order['error']}"
            return result

        result['orders'].append(order)

        # 设置止盈
        if tp_price:
            tp_order = self.futures_new_order(
                symbol=symbol,
                side='SELL',
                order_type='TAKE_PROFIT_MARKET',
                stop_price=tp_price,
                close_position=True
            )
            result['orders'].append(tp_order)

        # 设置止损
        if sl_price:
            sl_order = self.futures_new_order(
                symbol=symbol,
                side='SELL',
                order_type='STOP_MARKET',
                stop_price=sl_price,
                close_position=True
            )
            result['orders'].append(sl_order)

        result['success'] = True
        return result

    def close_long(self, symbol: str, quantity: float = None) -> Dict:
        """平多仓"""
        if quantity:
            return self.futures_new_order(
                symbol=symbol,
                side='SELL',
                order_type='MARKET',
                quantity=quantity,
                reduce_only=True
            )
        else:
            return self.futures_new_order(
                symbol=symbol,
                side='SELL',
                order_type='MARKET',
                close_position=True
            )

    def get_position(self, symbol: str) -> Optional[Dict]:
        """获取当前持仓"""
        positions = self.futures_position_info(symbol)
        if isinstance(positions, list):
            for pos in positions:
                if pos['symbol'] == symbol and float(pos['positionAmt']) != 0:
                    return {
                        'symbol': pos['symbol'],
                        'side': 'LONG' if float(pos['positionAmt']) > 0 else 'SHORT',
                        'quantity': abs(float(pos['positionAmt'])),
                        'entry_price': float(pos['entryPrice']),
                        'unrealized_pnl': float(pos['unRealizedProfit']),
                        'leverage': int(pos['leverage']),
                        'margin': float(pos['isolatedMargin']) if pos['marginType'] == 'isolated' else 0
                    }
        return None

    def get_balance(self, asset: str = 'USDT') -> float:
        """获取可用余额"""
        balances = self.futures_account_balance()
        if isinstance(balances, list):
            for b in balances:
                if b['asset'] == asset:
                    return float(b['availableBalance'])
        return 0.0


# 测试连接
def test_connection(api_key: str, api_secret: str, testnet: bool = False) -> Dict:
    """测试API连接"""
    api = BinanceAPI(api_key, api_secret, testnet)

    # 测试公开API
    price = api.futures_ticker_price('BTCUSDT')
    if 'error' in price:
        return {'success': False, 'error': f"公开API连接失败: {price['error']}"}

    # 测试私有API
    balance = api.futures_account_balance()
    if 'error' in balance:
        return {'success': False, 'error': f"私有API连接失败: {balance['error']}"}

    return {'success': True, 'price': price, 'balance': balance}
