"""
마켓 메이킹 전략
현재가 양쪽에 매수/매도 주문을 배치하여 스프레드 수익을 얻으면서 거래량 생성
"""
import time
import logging
from typing import Dict, List, Optional
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class MarketMakingStrategy(BaseStrategy):
    """
    마켓 메이킹 전략

    설정 파라미터:
    - spread_percent: 스프레드 비율 (%)
    - order_amount: 주문 수량
    - max_position: 최대 보유 수량
    - order_refresh_seconds: 주문 갱신 주기 (초)
    - min_profit_percent: 최소 수익률 (%)
    """

    def __init__(self, exchange, symbol: str, config: Dict):
        super().__init__(exchange, symbol, config)

        # 설정값 로드
        self.spread_percent = config.get('spread_percent', 0.1)
        self.order_amount = config.get('order_amount', 0.001)
        self.max_position = config.get('max_position', 0.01)
        self.order_refresh_seconds = config.get('order_refresh_seconds', 10)
        self.min_profit_percent = config.get('min_profit_percent', 0.05)

        # 상태 변수
        self.last_order_time = 0
        self.buy_order_id = None
        self.sell_order_id = None
        self.filled_buys = []  # 체결된 매수 주문 (평균단가 계산용)

        logger.info(f"마켓 메이킹 전략 설정: 스프레드={self.spread_percent}%, "
                   f"주문량={self.order_amount}, 최대포지션={self.max_position}")

    def start(self):
        """전략 시작"""
        logger.info(f"{self.symbol} 마켓 메이킹 전략 시작")
        self.is_running = True
        self.place_orders()

    def stop(self):
        """전략 중지"""
        logger.info(f"{self.symbol} 마켓 메이킹 전략 중지")
        self.is_running = False
        self.cancel_all_orders()

    def update(self):
        """전략 업데이트 (메인 루프에서 호출)"""
        if not self.is_running:
            return

        try:
            # 주문 상태 확인
            self.check_filled_orders()

            # 주문 갱신 주기 체크
            current_time = time.time()
            if current_time - self.last_order_time >= self.order_refresh_seconds:
                self.refresh_orders()
                self.last_order_time = current_time

        except Exception as e:
            logger.error(f"전략 업데이트 중 오류: {e}", exc_info=True)

    def place_orders(self):
        """매수/매도 주문 배치"""
        try:
            # 현재 시장 상황 조회
            mid_price = self.get_mid_price()
            position = self.get_position()

            base_currency = self.symbol.split('/')[0]
            base_available = position['base']['free']
            quote_available = position['quote']['free']

            # 주문 가격 계산
            spread_rate = self.spread_percent / 100
            buy_price = mid_price * (1 - spread_rate / 2)
            sell_price = mid_price * (1 + spread_rate / 2)

            # 거래소 규격에 맞게 반올림
            buy_price = self.exchange.round_price(self.symbol, buy_price)
            sell_price = self.exchange.round_price(self.symbol, sell_price)
            order_amount = self.exchange.round_amount(self.symbol, self.order_amount)

            logger.info(f"주문 배치: 매수={buy_price:.8f}, 매도={sell_price:.8f}, 수량={order_amount:.8f}")

            # 매수 주문 (보유 수량이 최대치 이하일 때만)
            if base_available < self.max_position:
                required_quote = buy_price * order_amount
                if quote_available >= required_quote:
                    try:
                        buy_order = self.exchange.create_limit_buy_order(
                            self.symbol, order_amount, buy_price
                        )
                        self.buy_order_id = buy_order['id']
                        logger.info(f"매수 주문 생성: {self.buy_order_id}")
                    except Exception as e:
                        logger.warning(f"매수 주문 실패: {e}")
                else:
                    logger.warning(f"매수 자금 부족: 필요={required_quote:.2f}, 보유={quote_available:.2f}")

            # 매도 주문 (보유 수량이 있을 때만)
            if base_available >= order_amount:
                try:
                    sell_order = self.exchange.create_limit_sell_order(
                        self.symbol, order_amount, sell_price
                    )
                    self.sell_order_id = sell_order['id']
                    logger.info(f"매도 주문 생성: {self.sell_order_id}")
                except Exception as e:
                    logger.warning(f"매도 주문 실패: {e}")
            else:
                logger.info(f"매도할 수량 부족: 필요={order_amount:.8f}, 보유={base_available:.8f}")

        except Exception as e:
            logger.error(f"주문 배치 중 오류: {e}", exc_info=True)

    def check_filled_orders(self):
        """체결된 주문 확인"""
        try:
            # 매수 주문 확인
            if self.buy_order_id:
                order = self.exchange.get_order(self.buy_order_id, self.symbol)
                if order['status'] == 'closed':
                    logger.info(f"매수 주문 체결: {self.buy_order_id} @ {order['price']}")
                    self.filled_buys.append({
                        'price': order['price'],
                        'amount': order['filled'],
                        'timestamp': time.time()
                    })
                    self.buy_order_id = None

            # 매도 주문 확인
            if self.sell_order_id:
                order = self.exchange.get_order(self.sell_order_id, self.symbol)
                if order['status'] == 'closed':
                    logger.info(f"매도 주문 체결: {self.sell_order_id} @ {order['price']}")
                    # 수익 계산
                    if self.filled_buys:
                        avg_buy_price = sum(b['price'] * b['amount'] for b in self.filled_buys) / \
                                       sum(b['amount'] for b in self.filled_buys)
                        profit_percent = ((order['price'] - avg_buy_price) / avg_buy_price) * 100
                        logger.info(f"수익률: {profit_percent:.3f}%")

                        # 체결된 매도 수량만큼 매수 기록에서 제거
                        sold_amount = order['filled']
                        remaining = sold_amount
                        while remaining > 0 and self.filled_buys:
                            if self.filled_buys[0]['amount'] <= remaining:
                                remaining -= self.filled_buys[0]['amount']
                                self.filled_buys.pop(0)
                            else:
                                self.filled_buys[0]['amount'] -= remaining
                                remaining = 0

                    self.sell_order_id = None

        except Exception as e:
            logger.error(f"주문 확인 중 오류: {e}", exc_info=True)

    def refresh_orders(self):
        """주문 갱신 (기존 주문 취소 후 새로운 주문 배치)"""
        try:
            logger.info("주문 갱신 중...")

            # 기존 미체결 주문 취소
            if self.buy_order_id:
                try:
                    self.exchange.cancel_order(self.buy_order_id, self.symbol)
                    self.buy_order_id = None
                except Exception as e:
                    logger.warning(f"매수 주문 취소 실패: {e}")

            if self.sell_order_id:
                try:
                    self.exchange.cancel_order(self.sell_order_id, self.symbol)
                    self.sell_order_id = None
                except Exception as e:
                    logger.warning(f"매도 주문 취소 실패: {e}")

            # 새로운 주문 배치
            self.place_orders()

            # 상태 로깅
            self.log_status()

        except Exception as e:
            logger.error(f"주문 갱신 중 오류: {e}", exc_info=True)

    def get_statistics(self) -> Dict:
        """전략 통계 조회"""
        position = self.get_position()
        base_currency = self.symbol.split('/')[0]
        quote_currency = self.symbol.split('/')[1]

        return {
            'strategy': 'MarketMaking',
            'symbol': self.symbol,
            'base_balance': position['base']['total'],
            'quote_balance': position['quote']['total'],
            'pending_buy': self.buy_order_id is not None,
            'pending_sell': self.sell_order_id is not None,
            'filled_buys': len(self.filled_buys),
        }
