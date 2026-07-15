# HTTPS 설정 — 클립보드 이미지 붙여넣기 활성화

피드백 작성 시 **클립보드 이미지 붙여넣기(Ctrl+V)** 는 브라우저의 보안 정책상
**HTTPS(보안 컨텍스트)** 에서만 동작한다. 사내 LAN의 평문 HTTP로는 막힌다.
인터넷 차단 환경이므로 공인 인증서를 받을 수 없어 **자체서명 인증서**를 만들고
각 개발 PC에 한 번 신뢰 등록한다. (openssl 불필요 — 파이썬 `cryptography` 사용)

전체 3단계: **① 서버에서 인증서 생성 → ② 서버 HTTPS 구동 → ③ 개발 PC에 인증서 신뢰 설치**

---

## ① 서버 PC A — 인증서 생성 (최초 1회)

```powershell
cd C:\rag\crypto          # 설치 폴더
.\packaging\gen_cert.ps1  # 기본 IP 192.168.155.89
# IP가 다르면:  .\packaging\gen_cert.ps1 192.168.1.50
```

`certs\` 폴더에 3개 파일이 생긴다:

| 파일 | 용도 |
|---|---|
| `cert.pem` | 서버 Streamlit 이 사용 (공개 인증서) |
| `key.pem`  | 서버 Streamlit 이 사용 (**개인키 — 외부 유출·커밋 금지**) |
| `cert.crt` | **개발 PC 신뢰 설치용** (내용은 cert.pem 과 동일, 확장자만 .crt) |

- 유효기간 10년, IP·127.0.0.1·localhost 를 SAN 에 포함.
- `certs\` 는 `.gitignore` 로 커밋 제외되어 있다(개인키 보호).

---

## ② 서버 PC A — HTTPS 로 구동

```powershell
.\packaging\start_server.ps1
```

`certs\cert.pem` + `key.pem` 이 있으면 자동으로 **HTTPS** 로 뜬다.
콘솔에 `https://192.168.155.89:8501` 이 출력되면 정상.
(인증서가 없으면 HTTP로 뜨며 클립보드 붙여넣기가 막힌다는 경고가 나온다.)

---

## ③ 각 개발 PC B — 인증서 신뢰 설치 (PC마다 1회)

서버의 `certs\cert.crt` 파일을 USB/공유폴더로 개발 PC에 복사한 뒤 **둘 중 하나**로 설치한다.

### 방법 A — 더블클릭 (가장 쉬움)
1. `cert.crt` 더블클릭 → **인증서 설치**
2. 저장소 위치: **로컬 컴퓨터** (관리자 권한) 또는 **현재 사용자**
3. "**모든 인증서를 다음 저장소에 저장**" 선택 → **찾아보기** →
   **신뢰할 수 있는 루트 인증 기관** 선택 → 완료
4. 보안 경고가 뜨면 "예"

### 방법 B — PowerShell (관리자)
```powershell
Import-Certificate -FilePath .\cert.crt -CertStoreLocation Cert:\LocalMachine\Root
# 또는:  certutil -addstore Root .\cert.crt
```

설치 후 브라우저를 **완전히 종료했다가 다시 실행**해야 적용된다.

---

## ④ 클라이언트 접속 주소 설정

- `open_client.bat` 또는 `rag-client.exe` 옆의 **`server.txt`** 를
  `https://192.168.155.89:8501` 로 설정(기본값도 이미 https).
- `rag-client.exe`(WebView2)도 Windows 신뢰 저장소를 사용하므로 ③ 설치가 되어 있어야 경고 없이 열린다.

---

## 확인 & 문제 해결

- **정상**: 주소창 자물쇠 아이콘, 경고 없음. 피드백 탭에서 이미지 캡처 후 붙여넣기 버튼/Ctrl+V 동작.
- **"연결이 비공개로 설정되어 있지 않습니다" / NET::ERR_CERT_AUTHORITY_INVALID**
  → ③ 신뢰 설치가 안 됐거나 브라우저 재시작 안 함. 다시 설치 후 브라우저 재실행.
- **"이 사이트에 연결할 수 없음"** → 서버 미기동 또는 IP/포트 불일치. `start_server.ps1` 콘솔의 주소 확인.
- **주소는 맞는데 인증서 오류** → 서버 IP 가 바뀌었는데 옛 인증서 사용. ① 을 새 IP로 다시 실행 후
  새 `cert.crt` 를 각 PC에 재설치.
- **인증서 갱신(10년 후 또는 IP 변경)**: ① 재실행 → 서버 재시작 → ③ 재설치.

> 개인키 `key.pem` 은 서버 밖으로 내보내지 말 것. 개발 PC에는 `cert.crt` (공개 인증서)만 배포한다.
