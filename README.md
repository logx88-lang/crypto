# Multi-Exchange Trading Bot

확장 가능한 멀티 거래소 지원 마켓메이킹 봇입니다. GRVT, Lighter, Variational, Pacifica 등 여러 거래소에서 동시에 거래할 수 있습니다.

## 주요 기능

- 🔄 **Multi-Exchange Support**: 4개 거래소 동시 지원 (GRVT, Lighter, Variational, Pacifica)
- 📊 **Market Making Strategy**: 스프레드 기반 마켓메이킹 전략
- ⚡ **Async Architecture**: 비동기 처리로 높은 성능
- 🔌 **Pluggable Design**: 새로운 거래소/전략 쉽게 추가 가능
- 🛡️ **Risk Management**: 포지션 자동 청산, 손실 제한 등
- 📝 **Comprehensive Logging**: 상세한 로깅 및 모니터링

## 프로젝트 구조

```
crypto/
├── src/
│   ├── exchanges/          # 거래소 어댑터
│   │   ├── base.py        # 추상 거래소 인터페이스
│   │   ├── grvt.py        # GRVT 구현
│   │   ├── lighter.py     # Lighter 구현
│   │   ├── variational.py # Variational 구현
│   │   └── pacifica.py    # Pacifica 구현
│   ├── strategies/         # 거래 전략
│   │   ├── base.py        # 추상 전략 인터페이스
│   │   └── market_making.py # 마켓메이킹 전략
│   ├── bot.py             # 메인 봇 로직
│   └── config.py          # 설정 관리
├── config/
│   ├── config.yaml        # 기본 설정
│   └── exchanges.yaml     # 거래소별 설정
├── tests/                  # 테스트
├── main.py                # 진입점
├── requirements.txt       # 의존성
└── .env.example          # 환경변수 템플릿
```

## 설치

### 1. 저장소 클론 및 의존성 설치

```bash
# Python 3.10+ 필요
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

### 2. 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열어 각 거래소의 API 키를 입력하세요:

```bash
# Bot Configuration
MODE=TEST  # TEST or LIVE

# Exchange API Keys
GRVT_API_KEY=your_api_key_here
GRVT_API_SECRET=your_api_secret_here
GRVT_PRIVATE_KEY=your_private_key_here

# Lighter, Variational, Pacifica도 동일하게 설정
```

### 3. 설정 커스터마이징

`config/config.yaml`에서 거래 파라미터 조정:

```yaml
trading:
  default_leverage: 5
  max_position_size: 0.001
  spread_bps: 10  # 10 basis points
  drift_threshold: 5
  order_refresh_interval: 60  # seconds
```

`config/exchanges.yaml`에서 각 거래소 설정:

```yaml
exchanges:
  grvt:
    enabled: true
    symbols:
      - BTC-USD-PERP
      - ETH-USD-PERP
    config:
      leverage: 5
      spread_bps: 10
      order_size: 0.001
```

## 사용법

### 기본 실행

```bash
python main.py
```

### TEST 모드 vs LIVE 모드

- **TEST 모드**: 안전한 테스트 환경 (기본값)
- **LIVE 모드**: 실제 거래 실행

```bash
# .env 파일에서 설정
MODE=TEST  # 또는 LIVE
```

⚠️ **경고**: LIVE 모드에서는 실제 자금이 사용됩니다!

## 아키텍처

### Exchange Adapter Pattern

각 거래소는 공통 인터페이스 `BaseExchange`를 구현합니다:

```python
class BaseExchange(ABC):
    async def create_order(...)
    async def cancel_order(...)
    async def get_position(...)
    async def get_balance(...)
    # ... 등
```

### Strategy Pattern

전략은 `BaseStrategy`를 상속받아 구현됩니다:

```python
class MarketMakingStrategy(BaseStrategy):
    async def initialize(...)
    async def run_cycle(...)
    async def cleanup(...)
```

### 새로운 거래소 추가하기

1. `src/exchanges/` 아래 새 파일 생성
2. `BaseExchange` 상속받아 구현
3. `src/exchanges/__init__.py`에 등록
4. `config/exchanges.yaml`에 설정 추가

예시:

```python
# src/exchanges/new_exchange.py
class NewExchange(BaseExchange):
    async def connect(self):
        # 구현
        pass

    async def create_order(self, ...):
        # 구현
        pass
    # ... 나머지 메서드 구현
```

### 새로운 전략 추가하기

1. `src/strategies/` 아래 새 파일 생성
2. `BaseStrategy` 상속받아 구현
3. 봇에서 전략 인스턴스 생성

## 필요한 자료

각 거래소의 실제 API 구현을 위해 다음 자료가 필요합니다:

### GRVT
- [ ] API 문서 URL
- [ ] WebSocket 엔드포인트
- [ ] 인증 방식 (API Key / Private Key)
- [ ] 주문 생성/취소 API 형식
- [ ] 포지션 조회 API 형식

### Lighter
- [ ] API 문서 URL
- [ ] WebSocket 엔드포인트
- [ ] 인증 방식
- [ ] API 스펙

### Variational
- [ ] API 문서 URL
- [ ] WebSocket 엔드포인트
- [ ] 인증 방식
- [ ] API 스펙

### Pacifica
- [ ] API 문서 URL
- [ ] WebSocket 엔드포인트
- [ ] 인증 방식
- [ ] API 스펙

## 현재 구현 상태

### ✅ 완료
- [x] 프로젝트 구조 설계
- [x] 설정 관리 시스템
- [x] 거래소 추상 인터페이스
- [x] 4개 거래소 어댑터 스켈레톤
- [x] 마켓메이킹 전략
- [x] 메인 봇 로직
- [x] 로깅 및 모니터링

### 🚧 진행 중 / TODO
- [ ] 각 거래소 API 실제 구현 (현재는 mock)
- [ ] WebSocket 실시간 데이터 연동
- [ ] 포지션 리스크 관리 고도화
- [ ] 백테스팅 시스템
- [ ] 웹 대시보드
- [ ] 알림 시스템 (Telegram, Discord 등)

## 리스크 관리

- **자동 포지션 청산**: `AUTO_CLOSE_POSITION=true`로 설정
- **일일 손실 제한**: `MAX_DAILY_LOSS` 설정
- **Stop Loss**: 각 거래소별 Stop Loss 설정 가능
- **레버리지 제한**: `MAX_LEVERAGE`로 최대 레버리지 제한

## 테스트

```bash
pytest tests/
```

## 로그

로그는 두 곳에 기록됩니다:
- 콘솔 출력 (컬러 포맷)
- `bot.log` 파일 (7일 보관, 100MB 로테이션)

## 주의사항

⚠️ **중요**:
- 이 봇은 교육 및 연구 목적으로 제공됩니다
- 실제 거래에 사용 시 발생하는 모든 손실은 사용자 책임입니다
- 충분한 테스트 없이 LIVE 모드 사용 금지
- API 키는 절대 공개하지 마세요

## 참고 자료

- [multi-perp-dex](https://github.com/NA-DEGEN-GIRL/multi-perp-dex)
- [standx_mm_bot](https://github.com/NA-DEGEN-GIRL/standx_mm_bot)

## 라이선스

MIT License

## 기여

이슈 및 PR 환영합니다!

---

**만든 날짜**: 2026-01-07
**버전**: 0.1.0