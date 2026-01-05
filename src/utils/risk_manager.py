"""
리스크 관리 모듈
손실 제한, 포지션 관리, 비정상 거래 감지 등
"""
import logging
from typing import Dict
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class RiskManager:
    """리스크 관리 클래스"""

    def __init__(self, config: Dict):
        """
        Args:
            config: 리스크 관리 설정
                - max_loss_percent: 최대 손실률 (%)
                - max_position_imbalance: 최대 포지션 불균형
                - daily_trade_limit: 일일 거래 횟수 제한
        """
        self.max_loss_percent = config.get('max_loss_percent', 5.0)
        self.max_position_imbalance = config.get('max_position_imbalance', 0.005)
        self.daily_trade_limit = config.get('daily_trade_limit', 10000)

        # 상태 변수
        self.initial_balance = None
        self.trade_count_today = 0
        self.last_reset_date = datetime.now().date()

        logger.info(f"리스크 관리 초기화: 최대손실={self.max_loss_percent}%, "
                   f"최대불균형={self.max_position_imbalance}")

    def set_initial_balance(self, base_amount: float, quote_amount: float, current_price: float):
        """초기 잔고 설정 (손익 계산 기준)"""
        # 모든 자산을 quote 통화로 환산
        total_in_quote = quote_amount + (base_amount * current_price)
        self.initial_balance = total_in_quote
        logger.info(f"초기 잔고 설정: {total_in_quote:.2f} (base={base_amount:.8f}, "
                   f"quote={quote_amount:.2f}, price={current_price:.2f})")

    def check_loss_limit(self, base_amount: float, quote_amount: float, current_price: float) -> bool:
        """
        손실 한도 체크

        Returns:
            True: 정상 범위
            False: 손실 한도 초과
        """
        if self.initial_balance is None:
            self.set_initial_balance(base_amount, quote_amount, current_price)
            return True

        # 현재 총 자산을 quote 통화로 환산
        current_total = quote_amount + (base_amount * current_price)

        # 손실률 계산
        loss_percent = ((self.initial_balance - current_total) / self.initial_balance) * 100

        if loss_percent > self.max_loss_percent:
            logger.error(f"손실 한도 초과! 손실률: {loss_percent:.2f}% "
                        f"(한도: {self.max_loss_percent}%)")
            logger.error(f"초기 잔고: {self.initial_balance:.2f}, 현재 잔고: {current_total:.2f}")
            return False

        if loss_percent > self.max_loss_percent * 0.7:
            logger.warning(f"손실 경고: {loss_percent:.2f}% (한도의 70% 도달)")

        return True

    def check_position_imbalance(self, base_amount: float, quote_amount: float,
                                  current_price: float, target_base: float) -> bool:
        """
        포지션 불균형 체크

        Args:
            base_amount: 현재 base 통화 보유량
            quote_amount: 현재 quote 통화 보유량
            current_price: 현재가
            target_base: 목표 base 통화 보유량

        Returns:
            True: 정상 범위
            False: 불균형 초과
        """
        # 목표 대비 실제 보유량 차이
        imbalance = abs(base_amount - target_base)

        if imbalance > self.max_position_imbalance:
            logger.warning(f"포지션 불균형: {imbalance:.8f} "
                         f"(현재={base_amount:.8f}, 목표={target_base:.8f})")
            return False

        return True

    def increment_trade_count(self):
        """거래 횟수 증가 (일일 제한 체크)"""
        # 날짜가 바뀌면 카운트 리셋
        today = datetime.now().date()
        if today != self.last_reset_date:
            self.trade_count_today = 0
            self.last_reset_date = today
            logger.info("일일 거래 카운트 리셋")

        self.trade_count_today += 1

    def check_trade_limit(self) -> bool:
        """
        일일 거래 횟수 제한 체크

        Returns:
            True: 정상 범위
            False: 제한 초과
        """
        if self.trade_count_today >= self.daily_trade_limit:
            logger.warning(f"일일 거래 횟수 제한 도달: {self.trade_count_today}/{self.daily_trade_limit}")
            return False

        if self.trade_count_today > self.daily_trade_limit * 0.9:
            logger.warning(f"일일 거래 횟수 90% 도달: {self.trade_count_today}/{self.daily_trade_limit}")

        return True

    def get_current_pnl(self, base_amount: float, quote_amount: float, current_price: float) -> Dict:
        """
        현재 손익 계산

        Returns:
            손익 정보 (총액, 손익, 손익률)
        """
        if self.initial_balance is None:
            self.set_initial_balance(base_amount, quote_amount, current_price)

        current_total = quote_amount + (base_amount * current_price)
        pnl = current_total - self.initial_balance
        pnl_percent = (pnl / self.initial_balance) * 100

        return {
            'initial_balance': self.initial_balance,
            'current_balance': current_total,
            'pnl': pnl,
            'pnl_percent': pnl_percent,
        }

    def should_stop_trading(self, base_amount: float, quote_amount: float, current_price: float) -> bool:
        """
        거래 중지 여부 판단

        Returns:
            True: 거래 중지해야 함
            False: 계속 거래 가능
        """
        # 손실 한도 체크
        if not self.check_loss_limit(base_amount, quote_amount, current_price):
            return True

        # 거래 횟수 제한 체크
        if not self.check_trade_limit():
            return True

        return False

    def log_status(self, base_amount: float, quote_amount: float, current_price: float):
        """리스크 관리 상태 로깅"""
        pnl_info = self.get_current_pnl(base_amount, quote_amount, current_price)

        logger.info("=== 리스크 관리 상태 ===")
        logger.info(f"초기 잔고: {pnl_info['initial_balance']:.2f}")
        logger.info(f"현재 잔고: {pnl_info['current_balance']:.2f}")
        logger.info(f"손익: {pnl_info['pnl']:+.2f} ({pnl_info['pnl_percent']:+.2f}%)")
        logger.info(f"일일 거래: {self.trade_count_today}/{self.daily_trade_limit}")
