"""
설정 관리 모듈
"""
import os
from dotenv import load_dotenv

# .env 파일 로드
load_dotenv()


class Config:
    """설정 클래스"""

    # 거래소 설정
    EXCHANGE = os.getenv('EXCHANGE', 'binance')
    API_KEY = os.getenv('API_KEY', '')
    API_SECRET = os.getenv('API_SECRET', '')
    TESTNET = os.getenv('TESTNET', 'false').lower() == 'true'

    # 거래 설정
    SYMBOL = os.getenv('SYMBOL', 'BTC/USDT')
    STRATEGY = os.getenv('STRATEGY', 'market_making')  # market_making, grid_trading

    # 마켓 메이킹 설정
    SPREAD_PERCENT = float(os.getenv('SPREAD_PERCENT', '0.1'))
    ORDER_AMOUNT = float(os.getenv('ORDER_AMOUNT', '0.001'))
    MAX_POSITION = float(os.getenv('MAX_POSITION', '0.01'))
    ORDER_REFRESH_SECONDS = int(os.getenv('ORDER_REFRESH_SECONDS', '10'))
    MIN_PROFIT_PERCENT = float(os.getenv('MIN_PROFIT_PERCENT', '0.05'))

    # 그리드 트레이딩 설정
    GRID_COUNT = int(os.getenv('GRID_COUNT', '10'))
    GRID_RANGE_PERCENT = float(os.getenv('GRID_RANGE_PERCENT', '2.0'))
    GRID_ORDER_AMOUNT = float(os.getenv('GRID_ORDER_AMOUNT', '0.0005'))
    REBALANCE_INTERVAL = int(os.getenv('REBALANCE_INTERVAL', '60'))

    # 리스크 관리
    MAX_LOSS_PERCENT = float(os.getenv('MAX_LOSS_PERCENT', '5.0'))
    MAX_POSITION_IMBALANCE = float(os.getenv('MAX_POSITION_IMBALANCE', '0.005'))
    DAILY_TRADE_LIMIT = int(os.getenv('DAILY_TRADE_LIMIT', '10000'))

    # 모니터링
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR = os.getenv('LOG_DIR', 'logs')
    STATUS_LOG_INTERVAL = int(os.getenv('STATUS_LOG_INTERVAL', '60'))

    # 텔레그램 알림 (선택사항)
    ENABLE_TELEGRAM = os.getenv('ENABLE_TELEGRAM', 'false').lower() == 'true'
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')

    @classmethod
    def get_strategy_config(cls):
        """전략별 설정 반환"""
        if cls.STRATEGY == 'market_making':
            return {
                'spread_percent': cls.SPREAD_PERCENT,
                'order_amount': cls.ORDER_AMOUNT,
                'max_position': cls.MAX_POSITION,
                'order_refresh_seconds': cls.ORDER_REFRESH_SECONDS,
                'min_profit_percent': cls.MIN_PROFIT_PERCENT,
            }
        elif cls.STRATEGY == 'grid_trading':
            return {
                'grid_count': cls.GRID_COUNT,
                'grid_range_percent': cls.GRID_RANGE_PERCENT,
                'order_amount': cls.GRID_ORDER_AMOUNT,
                'rebalance_interval': cls.REBALANCE_INTERVAL,
            }
        else:
            raise ValueError(f"알 수 없는 전략: {cls.STRATEGY}")

    @classmethod
    def get_risk_config(cls):
        """리스크 관리 설정 반환"""
        return {
            'max_loss_percent': cls.MAX_LOSS_PERCENT,
            'max_position_imbalance': cls.MAX_POSITION_IMBALANCE,
            'daily_trade_limit': cls.DAILY_TRADE_LIMIT,
        }

    @classmethod
    def validate(cls):
        """설정 검증"""
        errors = []

        if not cls.API_KEY:
            errors.append("API_KEY가 설정되지 않았습니다")
        if not cls.API_SECRET:
            errors.append("API_SECRET가 설정되지 않았습니다")

        if cls.STRATEGY not in ['market_making', 'grid_trading']:
            errors.append(f"지원하지 않는 전략: {cls.STRATEGY}")

        if cls.SPREAD_PERCENT <= 0:
            errors.append("SPREAD_PERCENT는 0보다 커야 합니다")

        if cls.ORDER_AMOUNT <= 0:
            errors.append("ORDER_AMOUNT는 0보다 커야 합니다")

        if errors:
            raise ValueError("설정 오류:\n" + "\n".join(errors))

        return True
