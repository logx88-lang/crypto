# 기여 가이드

이 프로젝트에 기여해 주셔서 감사합니다!

## 새로운 거래소 추가하기

1. `src/exchanges/` 디렉토리에 새 파일 생성 (예: `new_exchange.py`)
2. `BaseExchange` 클래스를 상속받아 구현
3. 모든 추상 메서드 구현 필수:
   - `connect()`, `disconnect()`
   - `create_order()`, `cancel_order()`, `cancel_all_orders()`
   - `get_open_orders()`, `get_position()`, `close_position()`
   - `get_balance()`, `get_ticker()`, `set_leverage()`
4. `src/exchanges/__init__.py`에 새 거래소 추가
5. `config/exchanges.yaml`에 설정 추가
6. 테스트 작성

### 예시 구조

```python
from .base import BaseExchange, Order, Position, Balance, Ticker
from typing import Dict, Any, List, Optional
from decimal import Decimal

class NewExchange(BaseExchange):
    def __init__(self, config: Dict[str, Any], credentials: Dict[str, str]):
        super().__init__(config, credentials)
        self.base_url = "https://api.newexchange.com"

    async def connect(self):
        # 연결 로직
        pass

    # ... 나머지 메서드 구현
```

## 새로운 전략 추가하기

1. `src/strategies/` 디렉토리에 새 파일 생성
2. `BaseStrategy` 클래스를 상속받아 구현
3. `initialize()`, `run_cycle()`, `cleanup()` 메서드 구현
4. 테스트 작성

## 코드 스타일

- PEP 8 준수
- Type hints 사용
- Docstrings 작성 (Google 스타일)
- 비동기 함수는 `async/await` 사용

## Pull Request 프로세스

1. Fork 및 브랜치 생성
2. 변경사항 커밋
3. 테스트 통과 확인
4. Pull Request 생성
5. 리뷰 대기

## 이슈 리포팅

버그 발견 시:
- 재현 가능한 예제 포함
- 환경 정보 (Python 버전, OS 등)
- 에러 메시지/로그
