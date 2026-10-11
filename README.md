# 🎙️ Silki (실키)

**QR 코드 하나로 시작하는 한국어 음성 주문 서비스**

고객은 테이블의 QR 코드를 스캔한 뒤 말로 메뉴를 주문합니다. 음성은 실시간으로 전사되고,
AI가 매장 메뉴 중에서 알맞은 후보를 찾아 되묻고 확인한 뒤 장바구니에 담습니다.
점주는 관리자 화면에서 메뉴를 관리하고, 들어오는 주문을 실시간(SSE)으로 받습니다.

> 메뉴·가격·장바구니·주문의 단일 진실 공급원은 Spring 백엔드입니다.
> AI 서비스는 **후보만 제안**하며, 주문을 확정하거나 장바구니를 직접 변경하지 않습니다.

---

## ✨ 주요 기능

**고객**
- QR 스캔 → 매장 주문 세션 생성
- 실시간 한국어 음성 인식 (CLOVA Speech, gRPC 스트리밍)
- 자연어 메뉴 추천 — "달지 않은 차가운 커피"처럼 말해도 의미 기반(pgvector)으로 검색
- 후보가 애매하면 최대 2개로 좁혀 되묻고, 온도(HOT/ICE) 같은 옵션을 보완
- 안내 음성(TTS) 재생, 장바구니·주문 상태 확인

**점주(관리자)**
- 로그인, 메뉴 등록·수정·품절 처리, 이미지 업로드
- 주문 내역 및 실시간 주문 알림(SSE)
- 메뉴가 바뀌면 AI 검색 인덱스 자동 재색인

---

## 🏗️ 아키텍처

```text
                       ┌──────────────── REST /api/* , SSE ────────────────┐
                       │                                                   ▼
┌──────────────┐       │                                   ┌─────────────────────────┐
│   Frontend   │───────┘                                   │   Backend (Spring Boot) │
│ React + Vite │                                           │  메뉴·장바구니·주문·인증 │
└──────┬───────┘                                           └───────┬─────────┬───────┘
       │  WSS /ai/ws (PCM16 16kHz 오디오 + 이벤트)                 │         │
       │  ※ Spring이 발급한 단기 RS256 JWT로 인증                  │ 재색인  │ JPA/Flyway
       ▼                                                           ▼ 요청    ▼
┌──────────────────────────┐                              ┌─────────────────────────┐
│   AI (FastAPI)           │◀──── 메뉴 뷰 ai_menu_source ──│  PostgreSQL + pgvector  │
│  턴 관리 · 추천 · 대화    │───── 메뉴 임베딩 저장 ───────▶│                         │
└──┬────────┬────────┬─────┘                              └─────────────────────────┘
   │        │        │
   ▼        ▼        ▼
 CLOVA    Gemini    TTS
 Speech   쿼리 정제  edge-tts / Fish Audio
```

**음성 주문 흐름**

1. FE가 QR에서 매장 ID를 읽고 Spring에 주문 세션을 만듭니다.
2. Spring이 `POST /api/v1/order-sessions/{id}/ai-token`으로 단기 AI 토큰(RS256 JWT)을 발급합니다.
3. FE가 AI의 `/ai/ws`에 연결하고 토큰으로 인증한 뒤 마이크 오디오를 스트리밍합니다.
4. AI가 발화를 전사 → Gemini로 검색 쿼리 정제 → pgvector로 메뉴 후보 검색 → 대화로 확정합니다.
5. 확정된 메뉴는 FE가 Spring API로 장바구니에 담고 주문합니다.

---

## 🛠️ 기술 스택

| 영역 | 기술 |
| --- | --- |
| Frontend | React 19, Vite 7, Tailwind CSS 4, React Router 7, AudioWorklet(PCM16), jsQR |
| Backend | Java 25, Spring Boot 4.1, Spring Security, Spring Data JPA, Flyway, springdoc-openapi, AWS S3 SDK |
| AI | Python 3.11+, FastAPI, uv, WebRTC VAD, CLOVA Speech(gRPC), Gemini, sentence embeddings, pgvector, edge-tts / Fish Audio |
| Database | PostgreSQL 16 + pgvector |
| Infra / CI | Docker, GitHub Actions |

---

## 📁 저장소 구조

```text
silki/
├── frontend/   React 고객·관리자 웹앱          → frontend/README.md
├── backend/    Spring Boot API 서버            → backend/README.md
├── ai/         FastAPI 음성 인식·메뉴 추천 서버  → ai/README.md
└── .github/workflows/ai-ci.yml   AI 서비스 CI (ai/ 변경 시 실행)
```

각 서비스의 상세 설계, 환경 변수 전체 목록, API 계약은 하위 폴더의 README와 `docs/`를 참고하세요.

- [AI WebSocket·재색인 API 계약](ai/docs/api-contract.md)
- [FE API DTO 및 요청 가이드](backend/docs/FE_API_GUIDE.md)
- [주문 SSE 가이드](backend/docs/SSE_GUIDE.md)

---

## 🚀 로컬 실행

### 사전 준비

- Node.js, Java 25, Python 3.11+ 및 [uv](https://docs.astral.sh/uv/), Docker
- Naver Cloud CLOVA Speech Secret Key, Gemini API 키 (Gemini 없이도 결정론적 폴백으로 동작)

### 1. 데이터베이스

AI 서비스는 백엔드가 Flyway로 만드는 `ai_menu_source` 뷰를 읽으므로
**백엔드와 AI는 같은 PostgreSQL을 사용해야 하며, pgvector 확장이 필요합니다.**
두 폴더의 `compose` 파일은 각각 5432 포트를 사용하므로 하나만 띄우세요.

```bash
cd ai
docker compose up -d postgres      # pgvector/pgvector:pg16 (DB/계정: silki)
```

그리고 `backend/.env`의 `SPRING_DATASOURCE_*`를 같은 DB(`jdbc:postgresql://localhost:5432/silki`, `silki`/`silki`)로 맞춥니다.

### 2. AI 서명 키 생성 (백엔드 ↔ AI)

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ai-jwt-private.pem
openssl pkey -in ai-jwt-private.pem -pubout -out ai-jwt-public.pem
```

개인키는 `backend/.env`의 `AI_JWT_PRIVATE_KEY`에, 공개키는 `ai/.env`의 `SILKI_AI_JWT_PUBLIC_KEY`에 넣습니다.
두 서비스 사이 내부 API 키(`AI_INTERNAL_API_KEY` = `SILKI_AI_INTERNAL_API_KEY`)도 같은 값으로 맞춥니다.
**`.pem` 파일과 `.env`는 절대 커밋하지 마세요.**

### 3. Backend (Spring Boot, :8080)

```bash
cd backend
cp .env.example .env    # 값 채우기
./gradlew bootRun
```

### 4. AI (FastAPI, :8000)

```bash
cd ai
cp .env.example .env    # CLOVA·Gemini 키, JWT 공개키 등 채우기
uv sync --frozen --extra dev
uv run python scripts/generate_clova_proto.py
uv run uvicorn silki_ai.app:app --reload
```

### 5. Frontend (Vite, :5173)

```bash
cd frontend
cp .env.example .env.local   # 로컬에서는 VITE_API_BASE_URL, VITE_AI_WS_URL 지정
npm install
npm run dev
```

> 브라우저 마이크는 보안 컨텍스트가 필요합니다. `localhost`가 아닌 곳에 배포할 때는 HTTPS/WSS를 사용하세요.

---

## ✅ 테스트

```bash
cd backend  && ./gradlew test
cd ai       && uv run pytest && uv run ruff check .
cd frontend && npm test && npm run lint
```

---

## 👥 팀 / 담당 역할

<!-- TODO: 팀원과 담당 역할을 채워주세요 -->

| 이름 | 역할 | 담당 |
| --- | --- | --- |
| | Frontend | |
| | Backend | |
| | AI | |
