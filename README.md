# 가상화폐 거래량 이벤트 자동매매 봇

거래소 토큰 거래량 이벤트 참가를 위한 자동매매 봇입니다. 최소한의 손실로 최대한의 거래량을 생성하는 것을 목표로 합니다.

## 주요 기능

### 지원 전략

1. **마켓 메이킹 (Market Making)**
   - 매수/매도 호가 양쪽에 주문 배치
   - 스프레드를 통한 수익 창출
   - 안정적인 거래량 생성
   - 낮은 리스크

2. **그리드 트레이딩 (Grid Trading)**
   - 가격 범위에 격자형 주문 배치
   - 횡보장에서 효과적
   - 자동화된 거래량 생성
   - 다수의 주문으로 큰 거래량 달성

### 리스크 관리

- 최대 손실률 제한
- 포지션 불균형 모니터링
- 일일 거래 횟수 제한
- 실시간 손익 추적

## 설치

### 요구사항

- Python 3.8 이상
- pip

### 설치 방법

```bash
# 저장소 클론
git clone <repository_url>
cd crypto

# 의존성 설치
pip install -r requirements.txt
```

## 설정

### 1. 환경 변수 설정

`.env.example` 파일을 `.env`로 복사하고 설정을 입력합니다:

```bash
cp .env.example .env
```

### 2. .env 파일 편집

```bash
# 거래소 API 설정
EXCHANGE=binance
API_KEY=your_api_key_here
API_SECRET=your_api_secret_here

# 거래 설정
SYMBOL=BTC/USDT
STRATEGY=market_making  # 또는 grid_trading

# 마켓 메이킹 설정
SPREAD_PERCENT=0.1        # 스프레드 0.1%
ORDER_AMOUNT=0.001        # 주문 수량
MAX_POSITION=0.01         # 최대 보유량

# 그리드 트레이딩 설정
GRID_COUNT=10             # 그리드 개수
GRID_RANGE_PERCENT=2.0    # 그리드 범위 2%
GRID_ORDER_AMOUNT=0.0005  # 각 그리드 주문 수량

# 리스크 관리
MAX_LOSS_PERCENT=5.0      # 최대 손실 5%
```

### 3. API 키 발급

각 거래소에서 API 키를 발급받아야 합니다:

- **Binance**: https://www.binance.com/en/my/settings/api-management
- **Upbit**: https://upbit.com/mypage/open_api_management
- **Bybit**: https://www.bybit.com/app/user/api-management

**중요**: API 키 생성 시 주의사항
- 현물 거래만 허용
- 출금 권한은 **절대 부여하지 않음**
- IP 화이트리스트 설정 권장

## 사용법

### 기본 실행

```bash
python main.py
```

### 전략별 실행

#### 마켓 메이킹 전략

```bash
# .env 파일에서 설정
STRATEGY=market_making
SPREAD_PERCENT=0.1
ORDER_AMOUNT=0.001

# 실행
python main.py
```

#### 그리드 트레이딩 전략

```bash
# .env 파일에서 설정
STRATEGY=grid_trading
GRID_COUNT=10
GRID_RANGE_PERCENT=2.0

# 실행
python main.py
```

### 종료

- `Ctrl+C`를 눌러 안전하게 종료
- 모든 미체결 주문이 자동으로 취소됩니다

## 프로젝트 구조

```
crypto/
├── src/
│   ├── exchange/          # 거래소 API 연동
│   │   ├── base_exchange.py
│   │   └── exchange_factory.py
│   ├── strategies/        # 거래 전략
│   │   ├── base_strategy.py
│   │   ├── market_making.py
│   │   └── grid_trading.py
│   ├── utils/             # 유틸리티
│   │   ├── risk_manager.py
│   │   └── logger.py
│   └── config.py          # 설정 관리
├── config/                # 설정 파일
├── logs/                  # 로그 파일
├── main.py               # 메인 실행 파일
├── requirements.txt      # 의존성
├── .env.example         # 환경 변수 예제
├── STRATEGY.md          # 전략 상세 설명
└── README.md            # 사용 가이드
```

## 전략 설명

### 마켓 메이킹

```
현재가: 10,000원

매수 주문: 9,995원 (현재가 - 0.05%)
매도 주문: 10,005원 (현재가 + 0.05%)

→ 양쪽 체결 시 10원 수익, 거래량 2배 생성
```

**장점:**
- 낮은 리스크
- 안정적인 수익
- 지속적인 거래량

**단점:**
- 급격한 가격 변동 시 손실 가능
- 한쪽만 체결될 수 있음

### 그리드 트레이딩

```
가격 범위: 9,500 ~ 10,500원
그리드 개수: 10개

매수 주문: 9,500, 9,600, 9,700, ...
매도 주문: 10,100, 10,200, 10,300, ...

→ 가격 변동 시 자동 체결
```

**장점:**
- 횡보장에서 매우 효과적
- 자동화가 쉬움
- 큰 거래량 생성

**단점:**
- 추세장에서 비효율적
- 초기 자본 더 필요

## 리스크 관리

### 손실 제한

- 최대 손실률 도달 시 자동 중지
- 실시간 손익 모니터링
- 경고 알림 (손실률 70% 도달 시)

### 포지션 관리

- 최대 보유량 제한
- 양쪽 포지션 균형 유지
- 자동 리밸런싱

### 거래 제한

- 일일 거래 횟수 제한
- API Rate Limit 준수
- 비정상 거래 감지

## 모니터링

### 로그 확인

```bash
# 실시간 로그 확인
tail -f logs/trading_bot_YYYYMMDD.log

# 최근 100줄
tail -n 100 logs/trading_bot_YYYYMMDD.log
```

### 로그 내용

- 거래 체결 내역
- 현재 포지션
- 손익 상태
- 리스크 지표
- 오류 및 경고

## 주의사항

### ⚠️ 반드시 읽어주세요

1. **테스트넷 먼저 사용**
   - 실제 자금 투입 전 테스트넷에서 충분히 테스트
   - `TESTNET=true`로 설정

2. **소액으로 시작**
   - 처음엔 최소 금액으로 시작
   - 안정성 확인 후 점진적 증액

3. **거래소 규정 확인**
   - 일부 거래소는 자동매매 제한
   - 이벤트 규칙 확인 (워시 트레이딩 감지)

4. **API 키 보안**
   - API 키를 절대 공유하지 마세요
   - .env 파일을 git에 커밋하지 마세요
   - 출금 권한은 절대 부여하지 마세요

5. **모니터링**
   - 정기적으로 봇 상태 확인
   - 비정상 동작 시 즉시 중지
   - 로그 파일 주기적 검토

6. **시장 리스크**
   - 급격한 가격 변동 대비
   - 유동성 부족 주의
   - 네트워크 장애 고려

## 문제 해결

### API 연결 오류

```
Error: Exchange connection failed
```

**해결 방법:**
1. API 키와 시크릿 확인
2. 거래소 API 서비스 상태 확인
3. IP 화이트리스트 설정 확인

### 주문 실패

```
Error: Insufficient balance
```

**해결 방법:**
1. 잔고 확인
2. 주문 수량 조정
3. 최소 주문량 확인

### 손실 한도 도달

```
Error: Loss limit exceeded
```

**해결 방법:**
1. 손실 원인 분석
2. 전략 파라미터 조정
3. MAX_LOSS_PERCENT 재설정

## 성능 최적화 팁

1. **수수료 최적화**
   - Maker 주문 활용 (지정가)
   - VIP 레벨 수수료 할인
   - 거래소 토큰 보유

2. **타이밍**
   - 변동성 적당한 시간대 선택
   - 유동성 높은 코인 선택
   - 이벤트 기간 집중

3. **파라미터 튜닝**
   - 백테스팅으로 최적 파라미터 찾기
   - 시장 상황에 따라 조정
   - 거래소별 특성 고려

## 백테스팅 (TODO)

과거 데이터로 전략 테스트 (개발 예정)

```bash
python backtest.py --strategy market_making --days 30
```

## 라이선스

이 프로젝트는 교육 목적으로만 사용하세요.

## 면책 조항

- 이 봇은 교육 및 연구 목적으로 제공됩니다
- 투자 손실에 대한 책임은 사용자에게 있습니다
- 사용 전 충분한 테스트를 권장합니다
- 거래소 규정을 반드시 확인하세요

## 기여

버그 리포트, 기능 제안 환영합니다!

## 연락처

문의사항이 있으시면 이슈를 등록해주세요.

---

**Happy Trading! 📈**
