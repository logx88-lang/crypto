"""
그리드 트레이딩 전략
일정 가격 범위에 격자형으로 매수/매도 주문을 배치하여 거래량 생성
"""
import time
import logging
from typing import Dict, List
from .base_strategy import BaseStrategy

logger = logging.getLogger(__name__)


class GridTradingStrategy(BaseStrategy):
    """
    그리드 트레이딩 전략

    설정 파라미터:
    - grid_count: 그리드 개수
    - grid_range_percent: 그리드 범위 (현재가 기준 %)
    - order_amount: 각 그리드의 주문 수량
    - rebalance_interval: 리밸런싱 주기 (초)
    """

    def __init__(self, exchange, symbol: str, config: Dict):
        super().__init__(exchange, symbol, config)

        # 설정값 로드
        self.grid_count = config.get('grid_count', 10)
        self.grid_range_percent = config.get('grid_range_percent', 2.0)
        self.order_amount = config.get('order_amount', 0.0005)
        self.rebalance_interval = config.get('rebalance_interval', 60)

        # 상태 변수
        self.grid_orders = []  # 그리드 주문 정보
        self.last_rebalance_time = 0
        self.center_price = None  # 그리드 중심가

        logger.info(f"그리드 트레이딩 전략 설정: 그리드={self.grid_count}개, "
                   f"범위={self.grid_range_percent}%, 주문량={self.order_amount}")

    def start(self):
        """전략 시작"""
        logger.info(f"{self.symbol} 그리드 트레이딩 전략 시작")
        self.is_running = True

        # 중심가 설정
        self.center_price = self.get_mid_price()
        logger.info(f"그리드 중심가: {self.center_price:.8f}")

        # 초기 그리드 배치
        self.setup_grid()

    def stop(self):
        """전략 중지"""
        logger.info(f"{self.symbol} 그리드 트레이딩 전략 중지")
        self.is_running = False
        self.cancel_all_grid_orders()

    def update(self):
        """전략 업데이트 (메인 루프에서 호출)"""
        if not self.is_running:
            return

        try:
            # 체결된 주문 확인 및 재배치
            self.check_and_refill_orders()

            # 리밸런싱 주기 체크
            current_time = time.time()
            if current_time - self.last_rebalance_time >= self.rebalance_interval:
                self.rebalance_grid()
                self.last_rebalance_time = current_time

        except Exception as e:
            logger.error(f"전략 업데이트 중 오류: {e}", exc_info=True)

    def setup_grid(self):
        """그리드 초기 설정"""
        try:
            logger.info("그리드 배치 시작...")

            # 그리드 가격 레벨 계산
            range_rate = self.grid_range_percent / 100
            price_lower = self.center_price * (1 - range_rate / 2)
            price_upper = self.center_price * (1 + range_rate / 2)
            grid_step = (price_upper - price_lower) / self.grid_count

            logger.info(f"그리드 범위: {price_lower:.8f} ~ {price_upper:.8f}")
            logger.info(f"그리드 간격: {grid_step:.8f}")

            # 현재가 조회
            current_price = self.get_current_price()

            # 그리드 주문 배치
            for i in range(self.grid_count + 1):
                grid_price = price_lower + (grid_step * i)
                grid_price = self.exchange.round_price(self.symbol, grid_price)

                # 현재가보다 낮으면 매수, 높으면 매도
                if grid_price < current_price:
                    self.place_grid_buy_order(grid_price, i)
                elif grid_price > current_price:
                    self.place_grid_sell_order(grid_price, i)

            logger.info(f"그리드 배치 완료: {len(self.grid_orders)}개 주문")
            self.log_grid_status()

        except Exception as e:
            logger.error(f"그리드 설정 중 오류: {e}", exc_info=True)

    def place_grid_buy_order(self, price: float, grid_level: int):
        """그리드 매수 주문 배치"""
        try:
            position = self.get_position()
            quote_available = position['quote']['free']

            order_amount = self.exchange.round_amount(self.symbol, self.order_amount)
            required_quote = price * order_amount

            if quote_available >= required_quote:
                order = self.exchange.create_limit_buy_order(self.symbol, order_amount, price)
                self.grid_orders.append({
                    'id': order['id'],
                    'side': 'buy',
                    'price': price,
                    'amount': order_amount,
                    'level': grid_level,
                    'status': 'open'
                })
                logger.debug(f"그리드 매수 주문 [{grid_level}]: {price:.8f} x {order_amount:.8f}")
            else:
                logger.warning(f"매수 자금 부족 (레벨 {grid_level}): 필요={required_quote:.2f}")

        except Exception as e:
            logger.warning(f"그리드 매수 주문 실패 (레벨 {grid_level}): {e}")

    def place_grid_sell_order(self, price: float, grid_level: int):
        """그리드 매도 주문 배치"""
        try:
            position = self.get_position()
            base_available = position['base']['free']

            order_amount = self.exchange.round_amount(self.symbol, self.order_amount)

            if base_available >= order_amount:
                order = self.exchange.create_limit_sell_order(self.symbol, order_amount, price)
                self.grid_orders.append({
                    'id': order['id'],
                    'side': 'sell',
                    'price': price,
                    'amount': order_amount,
                    'level': grid_level,
                    'status': 'open'
                })
                logger.debug(f"그리드 매도 주문 [{grid_level}]: {price:.8f} x {order_amount:.8f}")
            else:
                logger.warning(f"매도 수량 부족 (레벨 {grid_level}): 필요={order_amount:.8f}")

        except Exception as e:
            logger.warning(f"그리드 매도 주문 실패 (레벨 {grid_level}): {e}")

    def check_and_refill_orders(self):
        """체결된 주문 확인 및 재배치"""
        try:
            for grid_order in self.grid_orders[:]:  # 복사본으로 순회
                if grid_order['status'] != 'open':
                    continue

                # 주문 상태 확인
                order = self.exchange.get_order(grid_order['id'], self.symbol)

                if order['status'] == 'closed':
                    # 체결 완료
                    logger.info(f"그리드 주문 체결 [{grid_order['level']}]: "
                              f"{grid_order['side']} @ {grid_order['price']:.8f}")

                    grid_order['status'] = 'filled'

                    # 반대 주문 배치
                    if grid_order['side'] == 'buy':
                        # 매수 체결 -> 위쪽에 매도 주문 배치
                        self.place_opposite_sell_order(grid_order)
                    else:
                        # 매도 체결 -> 아래쪽에 매수 주문 배치
                        self.place_opposite_buy_order(grid_order)

        except Exception as e:
            logger.error(f"주문 확인 중 오류: {e}", exc_info=True)

    def place_opposite_sell_order(self, filled_buy_order: Dict):
        """매수 체결 후 매도 주문 배치"""
        try:
            # 매수가보다 약간 높은 가격에 매도
            sell_price = filled_buy_order['price'] * (1 + self.grid_range_percent / 100 / self.grid_count)
            sell_price = self.exchange.round_price(self.symbol, sell_price)

            position = self.get_position()
            base_available = position['base']['free']

            if base_available >= filled_buy_order['amount']:
                order = self.exchange.create_limit_sell_order(
                    self.symbol,
                    filled_buy_order['amount'],
                    sell_price
                )
                self.grid_orders.append({
                    'id': order['id'],
                    'side': 'sell',
                    'price': sell_price,
                    'amount': filled_buy_order['amount'],
                    'level': filled_buy_order['level'] + 0.5,  # 중간 레벨
                    'status': 'open',
                    'paired_with': filled_buy_order['id']
                })
                logger.info(f"매도 주문 배치: {sell_price:.8f} (매수가 {filled_buy_order['price']:.8f})")

        except Exception as e:
            logger.warning(f"반대 매도 주문 실패: {e}")

    def place_opposite_buy_order(self, filled_sell_order: Dict):
        """매도 체결 후 매수 주문 배치"""
        try:
            # 매도가보다 약간 낮은 가격에 매수
            buy_price = filled_sell_order['price'] * (1 - self.grid_range_percent / 100 / self.grid_count)
            buy_price = self.exchange.round_price(self.symbol, buy_price)

            position = self.get_position()
            quote_available = position['quote']['free']
            required_quote = buy_price * filled_sell_order['amount']

            if quote_available >= required_quote:
                order = self.exchange.create_limit_buy_order(
                    self.symbol,
                    filled_sell_order['amount'],
                    buy_price
                )
                self.grid_orders.append({
                    'id': order['id'],
                    'side': 'buy',
                    'price': buy_price,
                    'amount': filled_sell_order['amount'],
                    'level': filled_sell_order['level'] - 0.5,  # 중간 레벨
                    'status': 'open',
                    'paired_with': filled_sell_order['id']
                })
                logger.info(f"매수 주문 배치: {buy_price:.8f} (매도가 {filled_sell_order['price']:.8f})")

        except Exception as e:
            logger.warning(f"반대 매수 주문 실패: {e}")

    def rebalance_grid(self):
        """그리드 리밸런싱 (가격이 크게 변동한 경우)"""
        try:
            current_price = self.get_current_price()
            price_change = abs(current_price - self.center_price) / self.center_price

            # 중심가에서 1% 이상 벗어나면 리밸런싱
            if price_change > 0.01:
                logger.info(f"그리드 리밸런싱: 가격 변동 {price_change*100:.2f}%")
                logger.info(f"이전 중심가: {self.center_price:.8f}, 현재가: {current_price:.8f}")

                # 모든 주문 취소
                self.cancel_all_grid_orders()

                # 새 중심가 설정
                self.center_price = current_price

                # 그리드 재배치
                self.setup_grid()

        except Exception as e:
            logger.error(f"그리드 리밸런싱 중 오류: {e}", exc_info=True)

    def cancel_all_grid_orders(self):
        """모든 그리드 주문 취소"""
        logger.info("그리드 주문 전체 취소 중...")
        for grid_order in self.grid_orders:
            if grid_order['status'] == 'open':
                try:
                    self.exchange.cancel_order(grid_order['id'], self.symbol)
                    grid_order['status'] = 'canceled'
                except Exception as e:
                    logger.warning(f"주문 취소 실패 {grid_order['id']}: {e}")

        self.grid_orders.clear()

    def log_grid_status(self):
        """그리드 상태 로깅"""
        open_orders = [o for o in self.grid_orders if o['status'] == 'open']
        buy_orders = [o for o in open_orders if o['side'] == 'buy']
        sell_orders = [o for o in open_orders if o['side'] == 'sell']

        logger.info(f"=== 그리드 상태 ===")
        logger.info(f"총 주문: {len(open_orders)}개 (매수: {len(buy_orders)}, 매도: {len(sell_orders)})")
        logger.info(f"중심가: {self.center_price:.8f}")

        if buy_orders:
            lowest_buy = min(o['price'] for o in buy_orders)
            highest_buy = max(o['price'] for o in buy_orders)
            logger.info(f"매수 주문 범위: {lowest_buy:.8f} ~ {highest_buy:.8f}")

        if sell_orders:
            lowest_sell = min(o['price'] for o in sell_orders)
            highest_sell = max(o['price'] for o in sell_orders)
            logger.info(f"매도 주문 범위: {lowest_sell:.8f} ~ {highest_sell:.8f}")

    def get_statistics(self) -> Dict:
        """전략 통계 조회"""
        position = self.get_position()
        open_orders = [o for o in self.grid_orders if o['status'] == 'open']
        filled_orders = [o for o in self.grid_orders if o['status'] == 'filled']

        return {
            'strategy': 'GridTrading',
            'symbol': self.symbol,
            'center_price': self.center_price,
            'grid_count': self.grid_count,
            'open_orders': len(open_orders),
            'filled_orders': len(filled_orders),
            'base_balance': position['base']['total'],
            'quote_balance': position['quote']['total'],
        }
