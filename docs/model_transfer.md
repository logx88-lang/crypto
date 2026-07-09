# 오프라인 모델 이전 가이드 (Ollama / 리랭커 / OCR)

> 대상: 온라인 개발 PC에서 모델을 받아 **USB로 폐쇄망 PC에 이전**하는 절차. 인터넷은 온라인 PC에서만.
> 오프라인 PC: Windows 11, Ollama 기설치. 배포 용량 제약 없음.

---

## 1. 정품 bge-m3 임베딩 재반입 (필수)

**배경**: 오프라인 PC의 기존 `bge-m3-FP16.gguf` 태그는 검증 결과 실제로 **nomic-bert(768d, ctx 2048)**
오라벨이었다(참고: `ollama show`에서 architecture=nomic-bert, params=136.73M, embedding length=768).
한국어 검색 품질을 위해 **정품 bge-m3(1024d, ~567M)** 를 반입한다.

### 1-A. 온라인 PC에서 받기
```bash
ollama pull bge-m3          # BAAI bge-m3, 1024차원 (F16 ≈ 1.2GB)
ollama show bge-m3          # architecture=bert, embedding length=1024 확인
```

### 1-B. 모델 파일 위치
Ollama는 모델을 아래에 저장한다(온라인/오프라인 동일 구조).
- Linux/macOS: `~/.ollama/models`
- Windows: `C:\Users\<사용자명>\.ollama\models`

구조:
```
models/
  manifests/registry.ollama.ai/library/bge-m3/latest   # 매니페스트(작음)
  blobs/sha256-....                                     # 실제 가중치(큼)
```

### 1-C. USB로 이전 (병합 복사)
1. 온라인 PC의 `models/manifests/.../bge-m3/` 와 매니페스트가 참조하는 `models/blobs/sha256-*` 를 USB로 복사.
2. 오프라인 PC의 동일 경로(`C:\Users\<사용자명>\.ollama\models`)에 **병합**(기존 blobs 유지, 새 파일 추가).
   - 매니페스트는 `manifests/registry.ollama.ai/library/bge-m3/` 폴더째 넣으면 된다.
   - blobs는 파일명이 해시라 충돌 없이 추가된다.
3. 폴더 통째 복사가 헷갈리면, 온라인 PC에서 `ollama pull` 후 `~/.ollama/models` 전체를 USB에 담아
   오프라인 PC 동일 경로에 병합해도 된다.

### 1-D. 오프라인 PC에서 검증
```bash
ollama list                 # bge-m3 표시 확인
ollama show bge-m3          # embedding length = 1024 확인
# 임베딩 차원 실측
curl http://localhost:11434/api/embeddings -d "{\"model\":\"bge-m3\",\"prompt\":\"테스트\"}"
#   → embedding 배열 길이가 1024면 정상
```

### 1-E. 오라벨 태그 정리(선택)
혼동 방지를 위해 잘못 라벨된 태그는 코드에서 사용하지 않는다. 필요 시:
```bash
ollama rm bge-m3-FP16.gguf  # (주의) 동일 blob을 nomic-embed-text가 공유하면 nomic 태그는 유지됨
```
> 애플리케이션 설정은 항상 정품 `bge-m3` 태그를 참조한다.

### (대안) GGUF + Modelfile 로 등록
`ollama pull` 대신 HuggingFace 등에서 bge-m3 GGUF를 받은 경우:
```
# Modelfile
FROM ./bge-m3-f16.gguf
```
```bash
ollama create bge-m3 -f Modelfile
```

---

## 2. 리랭커 bge-reranker-v2-m3 (MVP 포함)

- 실행 방식: `sentence-transformers` CrossEncoder(**CPU**, torch CPU).
- 온라인 PC에서 모델 가중치를 받아 폴더째 USB로 이전(HuggingFace 형식, ~2.2GB).
- 오프라인에서 로컬 경로로 로드(네트워크 접근 없이).
```python
from sentence_transformers import CrossEncoder
reranker = CrossEncoder(r"C:\models\bge-reranker-v2-m3")  # 로컬 경로
```
- 상향(하드웨어 개선) 시 torch CUDA로 교체해 GPU 가속.

---

## 3. OCR 모델 (Phase 3, 도입 확정 시)

- PaddleOCR(kor+eng): 온라인 PC에서 인식/검출 모델 파일을 받아 USB로 이전, 오프라인에서 로컬 경로 지정.
- 인제스천 시점에만 동작하므로 질의 VRAM과 무경합.

---

## 4. 체크리스트

- [ ] `ollama pull bge-m3` (온라인) → USB → 오프라인 병합 → `ollama show bge-m3` 1024d 확인
- [ ] 임베딩 차원 실측(curl) 1024 확인
- [ ] 리랭커 가중치 로컬 경로 배치 + CrossEncoder 로드 확인
- [ ] (Phase3) OCR 모델 배치
- [ ] 애플리케이션 설정에서 임베딩 태그 = 정품 `bge-m3` 로 지정
