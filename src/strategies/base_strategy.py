"""
거래 전략 기본 클래스
"""
from abc import ABC, abstractmethod
from typing import Dict, List
import logging

logger = logging.getLogger(__name__)


class BaseStrategy(ABC):
    """모든 거래 전략의 기본 클래스"""

    def __init__(self, exchange, symbol: str, config: Dict):
        """
        Args:
            exchange: BaseExchange 객체
            symbol: 거래 심볼 (예: BTC/USDT)
            config: 전략 설정
        """
        self.exchange = exchange
        self.symbol = symbol
        self.config = config
        self.is_running = False
        self.active_orders = {}  # 활성 주문 관리

        logger.info(f"{self.__class__.__name__} 초기화: {symbol}")

    @abstractmethod
    def start(self):
        """전략 시작"""
        pass

    @abstractmethod
    def stop(self):
        """전략 중지"""
        pass

    @abstractmethod
    def update(self):
        """전략 업데이트 (메인 루프에서 호출)"""
        pass

    def get_current_price(self) -> float:
        """현재가 조회"""
        ticker = self.exchange.get_ticker(self.symbol)
        return ticker['last']

    def get_bid_ask(self) -> tuple:
        """매수/매도 호가 조회"""
        ticker = self.exchange.get_ticker(self.symbol)
        return ticker['bid'], ticker['ask']

    def get_mid_price(self) -> float:
        """중간가 계산"""
        bid, ask = self.get_bid_ask()
        return (bid + ask) / 2

    def cancel_all_orders(self):
        """모든 주문 취소"""
        logger.info(f"{self.symbol} 모든 주문 취소 중...")
        self.exchange.cancel_all_orders(self.symbol)
        self.active_orders.clear()

    def get_position(self) -> Dict:
        """현재 포지션 조회"""
        base_currency = self.symbol.split('/')[0]  # BTC/USDT -> BTC
        quote_currency = self.symbol.split('/')[1]  # BTC/USDT -> USDT

        base_balance = self.exchange.get_balance(base_currency)
        quote_balance = self.exchange.get_balance(quote_currency)

        return {
            'base': base_balance,
            'quote': quote_balance,
        }

    def log_status(self):
        """현재 상태 로깅"""
        position = self.get_position()
        current_price = self.get_current_price()

        base_currency = self.symbol.split('/')[0]
        quote_currency = self.symbol.split('/')[1]

        logger.info(f"=== {self.symbol} 현재 상태 ===")
        logger.info(f"현재가: {current_price:.8f}")
        logger.info(f"{base_currency} 잔고: {position['base']['total']:.8f} "
                   f"(사용가능: {position['base']['free']:.8f})")
        logger.info(f"{quote_currency} 잔고: {position['quote']['total']:.2f} "
                   f"(사용가능: {position['quote']['free']:.2f})")
        logger.info(f"활성 주문: {len(self.active_orders)}개")
