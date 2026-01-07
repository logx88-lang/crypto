# 상세 설치 가이드

## 1. 시스템 요구사항

- Python 3.10 이상
- 안정적인 인터넷 연결
- 최소 2GB RAM
- 각 거래소의 API 계정

## 2. 단계별 설치

### Step 1: Python 환경 설정

```bash
# Python 버전 확인
python --version  # 3.10 이상이어야 함

# 가상 환경 생성
python -m venv venv

# 가상 환경 활성화
# Linux/Mac:
source venv/bin/activate
# Windows:
venv\Scripts\activate
```

### Step 2: 의존성 설치

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### Step 3: 환경 변수 설정

```bash
# .env.example을 .env로 복사
cp .env.example .env

# .env 파일 편집
nano .env  # 또는 원하는 에디터 사용
```

필수 설정:
```
MODE=TEST
GRVT_API_KEY=your_key
GRVT_API_SECRET=your_secret
# ... 기타 거래소
```

### Step 4: 거래소 API 키 발급

#### GRVT
1. https://grvt.io 접속
2. 계정 생성 후 로그인
3. API 설정 메뉴에서 API 키 발급
4. Read/Write 권한 설정
5. `.env`에 키 입력

#### Lighter
1. https://lighter.xyz 접속
2. (동일한 프로세스)

#### Variational
1. https://variational.io 접속
2. (동일한 프로세스)

#### Pacifica
1. https://pacifica.exchange 접속
2. (동일한 프로세스)

### Step 5: 설정 커스터마이징

#### config/config.yaml

```yaml
bot:
  mode: TEST  # 반드시 TEST로 시작!
  log_level: INFO

trading:
  default_leverage: 5  # 초보자는 3-5 추천
  spread_bps: 10       # 시장 상황에 따라 조정
  order_refresh_interval: 60
```

#### config/exchanges.yaml

```yaml
exchanges:
  grvt:
    enabled: true  # 처음엔 하나만 활성화 추천
    testnet: true  # 테스트넷 사용
    symbols:
      - BTC-USD-PERP  # 적은 수로 시작
```

### Step 6: 테스트 실행

```bash
# 봇 실행 전 테스트
pytest tests/

# 봇 실행 (TEST 모드)
python main.py
```

### Step 7: 모니터링

실행 중 다른 터미널에서 로그 확인:
```bash
tail -f bot.log
```

## 3. 일반적인 문제 해결

### 문제 1: ModuleNotFoundError
```bash
# 해결: 의존성 재설치
pip install -r requirements.txt --force-reinstall
```

### 문제 2: API 인증 실패
- API 키 확인
- testnet/mainnet URL 확인
- 권한 설정 확인

### 문제 3: 연결 에러
- 인터넷 연결 확인
- 방화벽 설정 확인
- VPN 사용 시 끄기

## 4. TEST에서 LIVE로 전환

⚠️ **매우 중요**

1. TEST 모드에서 최소 1주일 이상 안정적으로 작동 확인
2. 모든 주요 시나리오 테스트
3. 리스크 관리 파라미터 검증
4. 소액으로 시작

```bash
# .env 파일 수정
MODE=LIVE

# exchanges.yaml 수정
testnet: false
```

## 5. 보안 체크리스트

- [ ] `.env` 파일이 `.gitignore`에 포함됨
- [ ] API 키를 절대 공개 저장소에 커밋하지 않음
- [ ] Read-only API 키로 먼저 테스트
- [ ] 2FA 활성화
- [ ] IP 화이트리스트 설정 (가능한 경우)

## 6. 성능 최적화

### 리소스 모니터링
```bash
# CPU/메모리 사용량 확인
top
htop
```

### 로그 레벨 조정
프로덕션에서는 `INFO` 또는 `WARNING` 레벨 사용

### 데이터베이스 (선택사항)
거래 기록을 저장하려면:
```bash
pip install sqlalchemy aiosqlite
```

## 7. 백업 및 복구

### 설정 백업
```bash
tar -czf bot-config-backup.tar.gz config/ .env
```

### 복구
```bash
tar -xzf bot-config-backup.tar.gz
```

## 8. 지원

- GitHub Issues: 버그 리포트
- Discussions: 일반 질문
- Email: (이메일 주소)
