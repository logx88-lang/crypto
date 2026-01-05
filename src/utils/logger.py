"""
로깅 설정 유틸리티
"""
import logging
import os
from datetime import datetime


def setup_logger(log_level: str = 'INFO', log_dir: str = 'logs'):
    """
    로거 설정

    Args:
        log_level: 로그 레벨 (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_dir: 로그 파일 저장 디렉토리
    """
    # 로그 디렉토리 생성
    os.makedirs(log_dir, exist_ok=True)

    # 로그 파일명 (날짜별)
    log_filename = os.path.join(log_dir, f"trading_bot_{datetime.now().strftime('%Y%m%d')}.log")

    # 로그 포맷
    log_format = '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    date_format = '%Y-%m-%d %H:%M:%S'

    # 루트 로거 설정
    logging.basicConfig(
        level=getattr(logging, log_level.upper()),
        format=log_format,
        datefmt=date_format,
        handlers=[
            # 파일 핸들러
            logging.FileHandler(log_filename, encoding='utf-8'),
            # 콘솔 핸들러
            logging.StreamHandler()
        ]
    )

    # CCXT 라이브러리 로그 레벨 조정 (너무 많은 로그 방지)
    logging.getLogger('ccxt').setLevel(logging.WARNING)

    logger = logging.getLogger(__name__)
    logger.info(f"로거 초기화 완료: {log_filename}")

    return logging.getLogger()
