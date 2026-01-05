#!/usr/bin/env python3
"""
가상화폐 거래량 이벤트용 자동매매 봇

사용법:
    python main.py

환경 변수 설정:
    .env 파일을 생성하고 필요한 설정을 입력하세요
    (.env.example 참고)
"""
import sys
import time
import signal
import logging
from src.config import Config
from src.exchange import ExchangeFactory
from src.strategies import MarketMakingStrategy, GridTradingStrategy
from src.utils import RiskManager, setup_logger

logger = logging.getLogger(__name__)
bot_running = True


def signal_handler(sig, frame):
    """시그널 핸들러 (Ctrl+C 등)"""
    global bot_running
    logger.info("종료 신호를 받았습니다. 봇을 안전하게 종료합니다...")
    bot_running = False


def main():
    """메인 실행 함수"""
    global bot_running

    # 시그널 핸들러 등록
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # 로거 설정
        setup_logger(Config.LOG_LEVEL, Config.LOG_DIR)
        logger.info("=" * 60)
        logger.info("거래량 이벤트 자동매매 봇 시작")
        logger.info("=" * 60)

        # 설정 검증
        logger.info("설정 검증 중...")
        Config.validate()
        logger.info("설정 검증 완료")

        # 설정 정보 출력
        logger.info(f"거래소: {Config.EXCHANGE}")
        logger.info(f"심볼: {Config.SYMBOL}")
        logger.info(f"전략: {Config.STRATEGY}")
        logger.info(f"테스트넷: {Config.TESTNET}")

        # 거래소 연결
        logger.info("거래소 연결 중...")
        exchange = ExchangeFactory.create(
            Config.EXCHANGE,
            Config.API_KEY,
            Config.API_SECRET,
            Config.TESTNET
        )
        logger.info("거래소 연결 완료")

        # 초기 잔고 확인
        base_currency = Config.SYMBOL.split('/')[0]
        quote_currency = Config.SYMBOL.split('/')[1]
        base_balance = exchange.get_balance(base_currency)
        quote_balance = exchange.get_balance(quote_currency)

        logger.info(f"{base_currency} 잔고: {base_balance['total']:.8f} "
                   f"(사용가능: {base_balance['free']:.8f})")
        logger.info(f"{quote_currency} 잔고: {quote_balance['total']:.2f} "
                   f"(사용가능: {quote_balance['free']:.2f})")

        # 리스크 관리자 초기화
        logger.info("리스크 관리자 초기화 중...")
        risk_manager = RiskManager(Config.get_risk_config())

        current_price = exchange.get_ticker(Config.SYMBOL)['last']
        risk_manager.set_initial_balance(
            base_balance['total'],
            quote_balance['total'],
            current_price
        )

        # 전략 초기화
        logger.info(f"{Config.STRATEGY} 전략 초기화 중...")
        strategy_config = Config.get_strategy_config()

        if Config.STRATEGY == 'market_making':
            strategy = MarketMakingStrategy(exchange, Config.SYMBOL, strategy_config)
        elif Config.STRATEGY == 'grid_trading':
            strategy = GridTradingStrategy(exchange, Config.SYMBOL, strategy_config)
        else:
            raise ValueError(f"지원하지 않는 전략: {Config.STRATEGY}")

        # 전략 시작
        logger.info("전략 시작...")
        strategy.start()

        # 메인 루프
        logger.info("메인 루프 시작 (Ctrl+C로 종료)")
        last_status_log = time.time()
        status_log_interval = Config.STATUS_LOG_INTERVAL

        while bot_running:
            try:
                # 전략 업데이트
                strategy.update()

                # 리스크 체크
                position = strategy.get_position()
                current_price = strategy.get_current_price()

                if risk_manager.should_stop_trading(
                    position['base']['total'],
                    position['quote']['total'],
                    current_price
                ):
                    logger.error("리스크 한도 도달! 봇을 중지합니다.")
                    break

                # 주기적 상태 로깅
                current_time = time.time()
                if current_time - last_status_log >= status_log_interval:
                    logger.info("-" * 60)
                    strategy.log_status()
                    risk_manager.log_status(
                        position['base']['total'],
                        position['quote']['total'],
                        current_price
                    )
                    logger.info("-" * 60)
                    last_status_log = current_time

                # CPU 부하 감소
                time.sleep(1)

            except KeyboardInterrupt:
                logger.info("키보드 인터럽트 감지")
                break
            except Exception as e:
                logger.error(f"메인 루프 오류: {e}", exc_info=True)
                time.sleep(5)  # 오류 시 잠시 대기

        # 종료 처리
        logger.info("봇 종료 중...")
        strategy.stop()

        # 최종 상태 출력
        logger.info("=" * 60)
        logger.info("최종 상태")
        logger.info("=" * 60)
        strategy.log_status()

        position = strategy.get_position()
        current_price = strategy.get_current_price()
        risk_manager.log_status(
            position['base']['total'],
            position['quote']['total'],
            current_price
        )

        logger.info("=" * 60)
        logger.info("봇 종료 완료")
        logger.info("=" * 60)

    except Exception as e:
        logger.error(f"치명적 오류: {e}", exc_info=True)
        sys.exit(1)


if __name__ == '__main__':
    main()
