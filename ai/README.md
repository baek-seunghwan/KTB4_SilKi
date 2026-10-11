# Silki AI

Silki AI는 실시간 한국어 음성 전사와 시맨틱 메뉴 추천을 제공하는 독립 구현 FastAPI 서비스입니다.

```text
React ── WSS /ai/ws ──> FastAPI ── gRPC ──> CLOVA Speech
                              │
                              ├──> Gemini 쿼리 정제
                              ├──> 문장 임베딩 ──> PostgreSQL + pgvector
                              └──> TTS ──> edge-tts (local) / Fish S2 Pro (production)
```

메뉴, 장바구니, 가격, 판매 가능 여부 및 주문에 관한 단일 진실 공급원은 계속 Spring Boot입니다.
이 서비스는 후보만 반환하며, 주문을 확정하거나 장바구니를 변경하지 않습니다.

## P1 동작

- 원시 PCM 스트리밍: 16 kHz, 모노, 부호 있는 16비트 리틀 엔디언.
- WebRTC VAD와 설정 가능한 PCM dBFS 에너지 임곗값을 함께 사용하는 잡음 내성 발화 감지.
- 1.5초의 무음 구간, 불완전한 한국어 발화에 대한 최대 2.5초 대기 시간, STT 문장 3초 정체 및 15초 최대 발화 안전장치를 사용하는 애플리케이션 소유 턴 수명 주기.
- 모든 비동기 이벤트에서 `sessionId`와 `turnId`를 분리해 사용.
- Gemini `gemini-3.5-flash-lite`는 최종 STT를 `search_query`, `quantity`, 메뉴 속성으로만 정제합니다. 응답이 유효하지 않거나 느리거나 실패하면 결정론적 추출로 대체하고 `degraded=true`를 설정합니다.
- 메뉴 이름, 설명, 카테고리, 태그를 대상으로 하는 매장 격리 pgvector 검색.
- `dialog.v1`에서는 누적 대화 상태로 후보를 최대 2개만 질문하고, 선택된 `menuId`를 고정한 채 온도 같은 옵션만 보완합니다.
- 원본 STT에 명시된 매장 메뉴명은 공백·문장부호를 제거한 canonical 값으로 먼저 확인해 Gemini 오정규화로 다른 메뉴가 선택되지 않게 하며, 단일 온도 메뉴는 DB가 허용한 HOT/ICE만 제안합니다.
- 최종 확인과 추가 주문 여부의 음성 답변을 `dialog.action`으로 반환하며, 실제 장바구니 반영과 화면 이동은 기존 FE/Spring 핸들러가 수행합니다.
- 권한 있는 메뉴 테이블에서 Spring이 트리거하는 리비전 안전 재색인.
- `RS256`, `iss=silki-be`, `aud=ai-ws`로 고정된 짧은 수명의 Spring 서명 액세스 토큰.
- 토큰의 `sub=orderSessionId`와 `storeId`를 WebSocket 세션에 함께 바인딩하고
  `session.ready`에서 클라이언트가 확인할 수 있도록 반환.
- 질문·최종 제안·장바구니 추가 완료 문장을 선택한 비스트리밍 TTS 공급자의 음성으로 `tts.audio`에 전달.
  TTS 실패는 기록만 하고 STT/추천/WebSocket 세션을 실패시키지 않음.

Redis 기반 일회성 `jti` 소진은 의도적으로 P2에 남겨 두었습니다.

## 저장소 구성

```text
silki_ai/                 FastAPI 애플리케이션 및 런타임 구성
  websocket_api.py        WSS 세션 오케스트레이션 및 이벤트 계약
  clova.py                CLOVA Speech gRPC 제공자 어댑터
  resources/              코드에서 직접 적용하는 CLOVA 키워드 목록
  turn_manager.py         애플리케이션 소유 발화 확정 처리
  nlp.py                  STT-검색 의도 정규화 및 폴백
  recommendation.py       임베딩 및 후보 검색 오케스트레이션
  pgvector_store.py       매장 격리 pgvector 검색
  tts.py                  edge-tts와 사설 Fish Audio 공급자 어댑터
  reindex.py              Spring 트리거 메뉴 임베딩 동기화
prompts/                  Gemini 쿼리 정제 프롬프트
evals/                    결정론적 평가 데이터 및 실행기
experiments/              비프로덕션 실험 작업 공간
proto/                    추적되는 공식 CLOVA 프로토콜과 생성 안내
tests/                    오프라인 단위 및 계약 테스트
```

이 저장소에서 “의도(Intent)”는 검색 쿼리와 메뉴 속성 추출을 뜻합니다.
메뉴 선택, 장바구니 변경 또는 주문 확정을 뜻하지 않습니다.

## 필수 설정

실제 값은 로컬 `.env` 또는 배포용 Secret Manager에 보관하고, 소스 제어에 포함하지 마세요.

| 값 | 환경 변수 | 제공자/담당자 |
| --- | --- | --- |
| CLOVA 스트리밍 Secret Key | `SILKI_AI_CLOVA_SECRET_KEY` | Naver Cloud CLOVA Speech Basic 장문 인식 도메인 |
| CLOVA gRPC 대상 | `SILKI_AI_CLOVA_GRPC_TARGET` | 고정 기본값: `clovaspeech-gw.ncloud.com:50051` |
| CLOVA 키워드 부스팅 | `SILKI_AI_CLOVA_KEYWORD_BOOSTING_ENABLED` | 기본값 `true`, 콘솔 대신 요청별 직접 부스팅 사용 |
| CLOVA 키워드 가중치 | `SILKI_AI_CLOVA_KEYWORD_WEIGHT` | `# weight: N` 헤더가 없는 그룹의 기본값 `5`; 허용 범위 `0`~`5` |
| CLOVA 키워드 파일 | `SILKI_AI_CLOVA_KEYWORD_FILE` | 선택값, 미설정 시 패키지의 208개 가중치 그룹 목록 사용 |
| VAD 최소 입력 레벨 | `SILKI_AI_VAD_MIN_RMS_DBFS` | 기본 `-45`; 허용 범위 `-80`~`-10` dBFS. 높일수록 잡음을 더 강하게 무시 |
| 발화 앞부분 보존 시간 | `SILKI_AI_AUDIO_PREROLL_MS` | 기본 `300`ms; VAD/dBFS 게이트가 열리기 직전 오디오를 이만큼 보관했다가 CLOVA에 먼저 흘려보내 첫 음절이 잘리지 않게 합니다. `0`은 비활성화 |
| STT 정체 확정 시간 | `SILKI_AI_TURN_TRANSCRIPT_STABLE_SECONDS` | 기본 `3`초; 잡음으로 VAD가 계속 켜져도 마지막으로 달라진 STT가 이 시간 동안 유지되면 확정, `0`은 비활성화 |
| 최대 발화 시간 | `SILKI_AI_TURN_MAX_SECONDS` | 기본 `15`초; 지속적인 배경음에도 턴을 끝내는 안전장치 |
| Gemini API 키 | `SILKI_AI_GEMINI_API_KEY` | Google AI Studio / Gemini API |
| Spring JWT 검증 공개 키 | `SILKI_AI_JWT_PUBLIC_KEY` | 풀스택/Spring 팀 |
| JWT 알고리즘/발급자/대상 | `SILKI_AI_JWT_ALGORITHMS`, `SILKI_AI_JWT_ISSUER`, `SILKI_AI_JWT_AUDIENCE` | 각각 `["RS256"]`, `silki-be`, `ai-ws` 고정 |
| JWT 최대 수명 | `SILKI_AI_JWT_MAX_TTL_SECONDS` | 기본 180초; Spring 기본 발급 수명 120초 |
| Spring-AI 간 공유 시크릿 | `SILKI_AI_INTERNAL_API_KEY` | Secret Manager로 생성 및 공유 |
| PostgreSQL 연결 URL | `SILKI_AI_DATABASE_URL` | 클라우드/데이터베이스 팀 |
| Spring 메뉴 호환 뷰 | `SILKI_AI_MENU_SOURCE_TABLE` | `public.ai_menu_source` |
| TTS 공급자 | `SILKI_AI_TTS_PROVIDER` | `edge`, `fish`, `disabled`; 코드 기본 `disabled`, 로컬 통합 스크립트는 `edge`를 명시 |
| edge-tts 음성 | `SILKI_AI_EDGE_TTS_VOICE` | 기본 `ko-KR-SunHiNeural`; 로컬/데모용 서드파티 온라인 TTS |
| edge-tts 속도 | `SILKI_AI_EDGE_TTS_RATE` | 기본 `-5%` |
| edge-tts 제한 | `SILKI_AI_TTS_TIMEOUT_SECONDS`, `SILKI_AI_TTS_MAX_AUDIO_BYTES` | 전체 요청 5초, 최대 5 MiB |
| Fish Audio 구형 사용 여부 | `SILKI_AI_FISH_TTS_ENABLED` | 호환성 전용; 새 설정에서는 `SILKI_AI_TTS_PROVIDER=fish` 사용 |
| Fish Audio 사설 origin | `SILKI_AI_FISH_TTS_BASE_URL` | 예: `http://10.0.2.15:8080` (`/v1/tts` 제외) |
| Fish Audio API Key | `SILKI_AI_FISH_TTS_API_KEY` | Secrets Manager/SSM에서 주입, 소스·이미지에 저장 금지 |
| Fish Audio 참조 음성 | `SILKI_AI_FISH_TTS_REFERENCE_ID` | 선택값; S2 Pro 모델 선택값이 아니라 저장된 화자 ID |
| Fish Audio 포맷/제한 | `SILKI_AI_FISH_TTS_FORMAT`, `SILKI_AI_FISH_TTS_TIMEOUT_SECONDS`, `SILKI_AI_FISH_TTS_MAX_AUDIO_BYTES` | 기본 `mp3`, 20초, 5 MiB |

CLOVA 스트리밍에는 CSR Client ID나 장문 인식 Invoke URL이 필요하지 않습니다.
기본 키워드 목록은 `silki_ai/resources/clova_keywords.txt`에서 한 줄에 하나씩 관리합니다.
`# weight: N` 헤더로 여러 부스팅 그룹을 만들 수 있으며 패키지 파일은 메뉴 고유명사 `5`,
사투리·축약어 `4`, 옵션·수량 표현 `3`의 208개 단어로 구성됩니다. 헤더가 없는 그룹에는
`SILKI_AI_CLOVA_KEYWORD_WEIGHT`를 사용합니다. 서버는 이 그룹들을 스트리밍 CONFIG 요청의
`keywordBoosting.boostings` 배열에 직접 넣습니다. 직접 부스팅을 켜면
`useDomainBoostings=false`이므로 콘솔에 저장된 도메인 키워드는 함께 적용하지 않습니다.
1,000개를 넘으면 시작에 실패하며 500개를 넘으면 인식 저하 가능성을 경고합니다.
Spring 서명 개인 키는 Spring에만 남아 있어야 하며, AI에는 공개 검증 키만 전달됩니다.
AI는 RSA 2048비트 이상의 공개 키만 허용하고 `sub`, `storeId`, `aud`, `iss`, `iat`, `exp`,
`jti`를 모두 검증합니다. 브라우저용 대칭 키나 HS256/ES256 폴백은 없습니다.
공개 임베딩 모델에는 Hugging Face 토큰이 필요하지 않습니다.

## 로컬 설정

요구 사항: Python 3.11 이상, uv, Docker, CLOVA Speech Basic 장문 인식 도메인, Gemini API 키.

```bash
cp .env.example .env
docker compose up -d postgres
uv sync --frozen --extra dev
source .venv/bin/activate
```

Linux/EC2에서는 일반 `pip install` 대신 위의 `uv sync --frozen` 또는 Docker 이미지를
사용해야 CPU 전용 PyTorch 인덱스와 잠금 파일이 그대로 적용됩니다.

저장소에 포함된 공식 `proto/nest.proto`로 클라이언트를 생성하세요.

```bash
python scripts/generate_clova_proto.py
```

Docker 빌드도 같은 `proto/nest.proto`를 사용해 이미지 내부에서 Python 스텁을 생성합니다.
따라서 로컬, CI, 배포 이미지가 동일한 CLOVA 계약을 사용합니다.

임베딩 모델은 공개되어 있어 API 키가 필요하지 않습니다. EC2 배포는 CPU 전용 PyTorch와
`device="cpu"`를 사용하므로 GPU 드라이버가 필요하지 않습니다. 프로덕션에서는 모델 캐시를
이미지에 포함하거나 Hugging Face 다운로드 이그레스/캐시를 허용하고
`SILKI_AI_EMBEDDING_PRELOAD=true`를 설정하세요.

API 실행:

```bash
uvicorn silki_ai.app:app --reload
```

상태 확인 엔드포인트는 `/health/live`, `/health/ready`입니다. 공개 WebSocket 경로는 `/ai/ws`이며, 인프라는 WebSocket 업그레이드를 활성화해 이 경로를 FastAPI로 라우팅해야 합니다.

준비 상태 확인에는 `public.ai_menu_source`와 AI 테이블, 실제로 파싱 가능한 RSA JWT 공개 키,
CLOVA Secret Key, 생성된 CLOVA 프로토콜 스텁 및 내부 재색인 자격 증명이 필요합니다.
`/health/ready`는 메뉴 뷰를 `menuSourceRelation`, AI 소유 테이블을 `databaseSchema`로 구분해 보고합니다.
Gemini 키가 없어도 서비스는 준비되지 않은 상태가 되지 않습니다. 결정론적 `degraded=true` 경로는 의도된 가용성 폴백이기 때문입니다.
TTS는 선택적/저하 허용 경로이므로 공급자 장애는 `/health/ready`나 추천 성공을 막지 않으며,
대화형 모달에는 `tts.unavailable`과 읽을 텍스트가 대신 전달됩니다.

## 연동

- [WebSocket 및 재색인 계약](docs/api-contract.md)
- [풀스택 및 클라우드 인수인계](docs/team-handoff.md)
- [Spring 메뉴 호환 뷰 검증 SQL](docs/spring-menu-contract.sql)
- [CLOVA proto 설정](proto/README.md)
- [Fish Audio S2 Pro AWS 배포](docs/fish-audio-aws.md)

## 검증

```bash
pytest
ruff check .
```

벡터의 숫자 배열 대신 저장 상태와 자연어 검색 결과를 사람이 읽을 수 있게 확인하려면
RDS에 접근 가능한 EC2에서 다음 명령을 실행합니다. 이 도구는 `SELECT`만 수행합니다.

```bash
uv run python scripts/inspect_vector_db.py --store-id <매장ID>
uv run python scripts/inspect_vector_db.py --store-id <매장ID> --query "달지 않은 차가운 커피"
```

명시적인 통합 환경을 구성하지 않는 한 테스트는 가짜 구현을 사용하며 CLOVA, Gemini 또는 PostgreSQL을 호출하지 않습니다.

레거시 MySQL/Qdrant 주문, 소유자 및 장바구니 엔드포인트는 이 서비스에서 노출하지 않습니다.
물리적 제거는 폐기된 코드가 아직 남아 있는 배포 환경에 한해 P2에서 별도로 정리할 항목입니다.
