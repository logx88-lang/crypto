"""
거래소 API 기본 클래스
CCXT 라이브러리를 사용하여 여러 거래소 지원
"""
import ccxt
import time
import logging
from typing import Dict, List, Optional, Tuple
from decimal import Decimal, ROUND_DOWN

logger = logging.getLogger(__name__)


class BaseExchange:
    """거래소 API 래퍼 클래스"""

    def __init__(self, exchange_id: str, api_key: str, api_secret: str, testnet: bool = False):
        """
        Args:
            exchange_id: 거래소 ID (binance, upbit, bybit 등)
            api_key: API 키
            api_secret: API 시크릿
            testnet: 테스트넷 사용 여부
        """
        self.exchange_id = exchange_id
        self.testnet = testnet

        # CCXT 거래소 객체 생성
        exchange_class = getattr(ccxt, exchange_id)
        self.exchange = exchange_class({
            'apiKey': api_key,
            'secret': api_secret,
            'enableRateLimit': True,
            'options': {
                'defaultType': 'spot',  # 현물 거래
            }
        })

        if testnet:
            self.exchange.set_sandbox_mode(True)
            logger.info(f"{exchange_id} 테스트넷 모드 활성화")

        # 거래소 정보 로드
        self.exchange.load_markets()
        logger.info(f"{exchange_id} 거래소 연결 완료")

    def get_ticker(self, symbol: str) -> Dict:
        """현재가 정보 조회"""
        try:
            ticker = self.exchange.fetch_ticker(symbol)
            return {
                'bid': ticker['bid'],  # 매수 호가
                'ask': ticker['ask'],  # 매도 호가
                'last': ticker['last'],  # 최종 체결가
                'high': ticker['high'],  # 24시간 최고가
                'low': ticker['low'],  # 24시간 최저가
                'volume': ticker['baseVolume'],  # 거래량
            }
        except Exception as e:
            logger.error(f"티커 조회 실패: {e}")
            raise

    def get_orderbook(self, symbol: str, limit: int = 20) -> Dict:
        """호가창 조회"""
        try:
            orderbook = self.exchange.fetch_order_book(symbol, limit)
            return {
                'bids': orderbook['bids'],  # 매수 호가 [[가격, 수량], ...]
                'asks': orderbook['asks'],  # 매도 호가 [[가격, 수량], ...]
                'timestamp': orderbook['timestamp']
            }
        except Exception as e:
            logger.error(f"호가창 조회 실패: {e}")
            raise

    def get_balance(self, currency: str = None) -> Dict:
        """잔고 조회"""
        try:
            balance = self.exchange.fetch_balance()
            if currency:
                return {
                    'free': balance['free'].get(currency, 0),  # 사용 가능
                    'used': balance['used'].get(currency, 0),  # 주문 중
                    'total': balance['total'].get(currency, 0)  # 총액
                }
            return balance
        except Exception as e:
            logger.error(f"잔고 조회 실패: {e}")
            raise

    def create_limit_buy_order(self, symbol: str, amount: float, price: float) -> Dict:
        """지정가 매수 주문"""
        try:
            order = self.exchange.create_limit_buy_order(symbol, amount, price)
            logger.info(f"매수 주문 생성: {symbol} {amount}@{price}, ID: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"매수 주문 실패: {e}")
            raise

    def create_limit_sell_order(self, symbol: str, amount: float, price: float) -> Dict:
        """지정가 매도 주문"""
        try:
            order = self.exchange.create_limit_sell_order(symbol, amount, price)
            logger.info(f"매도 주문 생성: {symbol} {amount}@{price}, ID: {order['id']}")
            return order
        except Exception as e:
            logger.error(f"매도 주문 실패: {e}")
            raise

    def cancel_order(self, order_id: str, symbol: str) -> Dict:
        """주문 취소"""
        try:
            result = self.exchange.cancel_order(order_id, symbol)
            logger.info(f"주문 취소: {order_id}")
            return result
        except Exception as e:
            logger.error(f"주문 취소 실패: {e}")
            raise

    def get_order(self, order_id: str, symbol: str) -> Dict:
        """주문 상태 조회"""
        try:
            order = self.exchange.fetch_order(order_id, symbol)
            return {
                'id': order['id'],
                'status': order['status'],  # open, closed, canceled
                'side': order['side'],  # buy, sell
                'price': order['price'],
                'amount': order['amount'],
                'filled': order['filled'],  # 체결된 수량
                'remaining': order['remaining'],  # 남은 수량
            }
        except Exception as e:
            logger.error(f"주문 조회 실패: {e}")
            raise

    def get_open_orders(self, symbol: str = None) -> List[Dict]:
        """미체결 주문 조회"""
        try:
            orders = self.exchange.fetch_open_orders(symbol)
            return orders
        except Exception as e:
            logger.error(f"미체결 주문 조회 실패: {e}")
            raise

    def cancel_all_orders(self, symbol: str) -> List[Dict]:
        """모든 미체결 주문 취소"""
        try:
            open_orders = self.get_open_orders(symbol)
            results = []
            for order in open_orders:
                result = self.cancel_order(order['id'], symbol)
                results.append(result)
            logger.info(f"{symbol} 모든 주문 취소 완료: {len(results)}개")
            return results
        except Exception as e:
            logger.error(f"전체 주문 취소 실패: {e}")
            raise

    def get_my_trades(self, symbol: str, limit: int = 100) -> List[Dict]:
        """최근 체결 내역 조회"""
        try:
            trades = self.exchange.fetch_my_trades(symbol, limit=limit)
            return trades
        except Exception as e:
            logger.error(f"체결 내역 조회 실패: {e}")
            raise

    def get_market_info(self, symbol: str) -> Dict:
        """마켓 정보 조회 (최소 주문량, 가격 단위 등)"""
        try:
            market = self.exchange.market(symbol)
            return {
                'min_amount': market['limits']['amount']['min'],
                'max_amount': market['limits']['amount']['max'],
                'min_price': market['limits']['price']['min'],
                'max_price': market['limits']['price']['max'],
                'amount_precision': market['precision']['amount'],
                'price_precision': market['precision']['price'],
            }
        except Exception as e:
            logger.error(f"마켓 정보 조회 실패: {e}")
            raise

    def round_amount(self, symbol: str, amount: float) -> float:
        """주문 수량을 거래소 규격에 맞게 반올림"""
        market_info = self.get_market_info(symbol)
        precision = market_info['amount_precision']

        decimal_amount = Decimal(str(amount))
        quantize_exp = Decimal('0.1') ** precision
        rounded = decimal_amount.quantize(quantize_exp, rounding=ROUND_DOWN)
        return float(rounded)

    def round_price(self, symbol: str, price: float) -> float:
        """주문 가격을 거래소 규격에 맞게 반올림"""
        market_info = self.get_market_info(symbol)
        precision = market_info['price_precision']

        decimal_price = Decimal(str(price))
        quantize_exp = Decimal('0.1') ** precision
        rounded = decimal_price.quantize(quantize_exp, rounding=ROUND_DOWN)
        return float(rounded)

    def get_trading_fees(self, symbol: str) -> Dict:
        """거래 수수료 조회"""
        try:
            # 대부분의 거래소는 maker/taker 수수료 구조
            market = self.exchange.market(symbol)
            return {
                'maker': market.get('maker', 0.001),  # 지정가 주문 수수료
                'taker': market.get('taker', 0.001),  # 시장가 주문 수수료
            }
        except Exception as e:
            logger.warning(f"수수료 조회 실패, 기본값 사용: {e}")
            return {'maker': 0.001, 'taker': 0.001}
