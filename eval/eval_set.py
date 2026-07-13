"""검색 평가셋 — 더미 문서 근거 질문 + 정답 판정용 substring.

relevance oracle: 검색된 청크의 text 에 `must_contain`(대소문자 무시)이 포함되면 관련 청크로 간주.
must_contain 은 해당 문서의 **정답 근거 문장/코드**로, 대체로 한 문서에만 등장하도록 선정.
`source` 는 참고 표기(판정에는 must_contain 사용).

질문 유형 균형:
- 정확매칭(코드/ID → BM25 유리): COIN_IN, OVERFLOW, 0x40, EQ-1001, hex 예시
- 의미/교차언어(→ dense 유리): "인식 안 될 때 조치", "장애 시 참조", "온도 250"
"""

EVAL = [
    {"q": "XM-200에서 코인 투입을 통지하는 명령 코드는 무엇입니까?",
     "must_contain": "COIN_IN", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "TG-15는 XM-200과 달리 어떤 프레임 시작·검증 방식을 사용합니까?",
     "must_contain": "SOH 시작", "source": "TG-15_sensor_gateway_protocol.docx"},
    {"q": "코인이 걸렸을 때(coin jam) 이벤트 코드는?",
     "must_contain": "COIN_JAM", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "XM-200의 시리얼 통신 속도와 프레임 형식은?",
     "must_contain": "8N1", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "TG-15의 통신 속도는 얼마입니까?",
     "must_contain": "19200bps", "source": "TG-15_sensor_gateway_protocol.docx"},
    {"q": "코인이 인식되지 않을 때 어떻게 조치하나요?",
     "must_contain": "투입구 잠금", "source": "faq_utf8.txt"},
    {"q": "온도 응답값이 250이면 실제 몇 도인가요?",
     "must_contain": "0.1도", "source": "faq_utf8.txt"},
    {"q": "정기 점검은 언제 실시합니까?",
     "must_contain": "첫째 주 월요일", "source": "notice_cp949.txt"},
    {"q": "코인 카운터 레지스터의 주소는?",
     "must_contain": "0x40", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "INIT 초기화 프레임의 hex 예시는?",
     "must_contain": "02 01 10 11 03", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "장애가 발생하면 어느 장을 참조해야 합니까?",
     "must_contain": "4장 문제해결", "source": "operation_manual.docx"},
    {"q": "자산번호 EQ-1001은 어떤 장비입니까?",
     "must_contain": "EQ-1001", "source": "equipment_list.xlsx"},
    {"q": "호퍼가 넘쳤을 때(overflow) 이벤트 코드는?",
     "must_contain": "OVERFLOW", "source": "XM-200_coin_controller_protocol.pdf"},
    {"q": "TG-15 패킷의 ADDR 필드는 무엇을 의미합니까?",
     "must_contain": "슬레이브 주소", "source": "TG-15_sensor_gateway_protocol.docx"},
    {"q": "상위 제어기는 XM-200을 무엇으로 제어합니까?",
     "must_contain": "RS-232로 XM-200", "source": "operation_manual.docx"},
    {"q": "500원을 지급하는 명령의 예시는?",
     "must_contain": "DISPENSE 500원", "source": "XM-200_coin_controller_protocol.pdf"},
]
