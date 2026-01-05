"""
거래소 팩토리 클래스
"""
from .base_exchange import BaseExchange


class ExchangeFactory:
    """거래소 객체 생성 팩토리"""

    @staticmethod
    def create(exchange_id: str, api_key: str, api_secret: str, testnet: bool = False) -> BaseExchange:
        """
        거래소 객체 생성

        Args:
            exchange_id: 거래소 ID (binance, upbit, bybit 등)
            api_key: API 키
            api_secret: API 시크릿
            testnet: 테스트넷 사용 여부

        Returns:
            BaseExchange: 거래소 객체
        """
        return BaseExchange(exchange_id, api_key, api_secret, testnet)
