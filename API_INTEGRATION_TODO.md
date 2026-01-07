# API 통합 TODO 리스트

이 파일은 각 거래소의 실제 API 통합을 위한 체크리스트입니다.

## 공통 필요 정보

각 거래소마다 다음 정보가 필요합니다:

### 1. API 엔드포인트
- [ ] Base URL (mainnet)
- [ ] Base URL (testnet)
- [ ] WebSocket URL (실시간 데이터)

### 2. 인증
- [ ] 인증 방식 (API Key, Private Key, JWT 등)
- [ ] 서명(Signature) 생성 방법
- [ ] 헤더 형식

### 3. API 메서드 스펙

#### 주문 관리
- [ ] 주문 생성 (POST /orders)
  - 요청 형식
  - 응답 형식
  - 에러 코드
- [ ] 주문 취소 (DELETE /orders/{id})
- [ ] 모든 주문 취소 (DELETE /orders)
- [ ] 주문 조회 (GET /orders)

#### 포지션 관리
- [ ] 포지션 조회 (GET /positions)
- [ ] 포지션 청산
- [ ] 레버리지 설정 (POST /leverage)

#### 계정 정보
- [ ] 잔고 조회 (GET /balance)
- [ ] 거래 내역 (GET /trades)

#### 시장 데이터
- [ ] 티커 조회 (GET /ticker)
- [ ] 오더북 (GET /orderbook)
- [ ] 최근 거래 (GET /trades/recent)

### 4. 심볼 형식
- [ ] 심볼 표기법 (BTC-USD-PERP, BTCUSDT 등)
- [ ] 심볼 정규화 로직

### 5. 제한사항
- [ ] Rate Limit (요청 제한)
- [ ] 최소/최대 주문 크기
- [ ] 가격 틱 사이즈
- [ ] 레버리지 범위

---

## GRVT

### 문서
- API Docs: (URL 필요)
- SDK: (있다면)

### 체크리스트
- [ ] 메인넷 URL 확인
- [ ] 테스트넷 URL 확인
- [ ] API 키 발급 방법 확인
- [ ] 주문 생성 API 구현
- [ ] 주문 취소 API 구현
- [ ] 포지션 조회 API 구현
- [ ] 잔고 조회 API 구현
- [ ] 티커 조회 API 구현
- [ ] WebSocket 연동
- [ ] 에러 처리
- [ ] 테스트 작성

### 구현 우선순위
1. 인증 및 연결
2. 티커 조회 (시장 데이터)
3. 잔고 조회
4. 주문 생성/취소
5. 포지션 관리
6. WebSocket 실시간 데이터

---

## Lighter

### 문서
- API Docs: (URL 필요)
- SDK: (있다면)

### 체크리스트
(GRVT와 동일한 구조)

---

## Variational

### 문서
- API Docs: (URL 필요)
- SDK: (있다면)

### 체크리스트
(GRVT와 동일한 구조)

---

## Pacifica

### 문서
- API Docs: (URL 필요)
- SDK: (있다면)

### 체크리스트
(GRVT와 동일한 구조)

---

## 구현 단계별 가이드

### Phase 1: 기본 연결 및 인증
```python
async def connect(self):
    # 1. HTTP 세션 생성
    self.session = aiohttp.ClientSession(headers=...)

    # 2. 인증 테스트
    response = await self._request("GET", "/account/info")

    # 3. 연결 상태 업데이트
    self._connected = True
```

### Phase 2: 시장 데이터
```python
async def get_ticker(self, symbol: str) -> Ticker:
    # 1. API 호출
    response = await self._request("GET", f"/market/ticker/{symbol}")

    # 2. 응답 파싱
    return Ticker(
        symbol=symbol,
        bid=Decimal(response["bid"]),
        ask=Decimal(response["ask"]),
        ...
    )
```

### Phase 3: 주문 관리
```python
async def create_order(self, symbol, side, type, size, price):
    # 1. 페이로드 생성
    payload = {
        "symbol": self.normalize_symbol(symbol),
        "side": side.value,
        "type": type.value,
        "size": str(size),
        "price": str(price),
    }

    # 2. 서명 생성 (필요한 경우)
    signature = self._sign(payload)

    # 3. API 호출
    response = await self._request("POST", "/orders", json=payload)

    # 4. Order 객체로 변환
    return Order(...)
```

### Phase 4: WebSocket 연동
```python
async def _subscribe_websocket(self, symbols):
    async with websockets.connect(self.ws_url) as ws:
        # 1. 구독 메시지 전송
        await ws.send(json.dumps({
            "op": "subscribe",
            "channel": "ticker",
            "symbols": symbols
        }))

        # 2. 메시지 수신
        async for message in ws:
            data = json.loads(message)
            # 처리...
```

---

## 테스트 계획

### 단위 테스트
- [ ] 심볼 정규화
- [ ] 주문 생성/파싱
- [ ] 에러 처리

### 통합 테스트
- [ ] 실제 API 연결 (testnet)
- [ ] 주문 생성 및 취소 플로우
- [ ] WebSocket 연결 안정성

### 부하 테스트
- [ ] Rate limit 준수
- [ ] 동시 요청 처리
- [ ] 장시간 실행 안정성

---

## 다음 단계

1. **정보 수집**: 각 거래소의 공식 문서 확인
2. **테스트넷 계정**: 각 거래소의 테스트넷 계정 생성
3. **Postman/Insomnia**: API 수동 테스트
4. **구현**: 한 거래소씩 차례로 구현
5. **테스트**: 각 구현 단계마다 테스트
6. **문서화**: API 특이사항 기록

---

## 필요한 도움

다음 정보를 제공해 주세요:

1. 각 거래소의 API 문서 링크
2. 테스트넷 접속 방법
3. API 키 발급 절차
4. 특별한 요구사항이나 제한사항
5. 기존에 작성한 코드나 예제 (있다면)

이 정보가 있으면 실제 API 통합을 바로 시작할 수 있습니다!
