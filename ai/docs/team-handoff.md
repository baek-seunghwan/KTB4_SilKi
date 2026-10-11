# 팀 인수인계

## 풀스택

- 마이크 오디오를 문서화된 PCM 형식으로 캡처하고 리샘플링합니다.
- Spring에서 짧은 수명의 AI 액세스 토큰을 받은 후 `/ai/ws`에 직접 연결합니다. Spring은 오디오를 프록시하지 않습니다.
- AI 결과는 후보로만 취급합니다. 장바구니를 업데이트하기 전 가격, 재고, 판매 가능 여부를 Spring에서 다시 검증합니다.
- 확인 후 최신 전체 장바구니 컨텍스트를 보내고, 오래된 `basedOnCartVersion` 결과는 거부합니다.
- `dialog.v1`의 `dialog.action`은 음성으로 누른 버튼에 해당합니다. `accept`, `reject`, `continue`, `finish`를 각각 기존 FE 버튼 핸들러에 연결하며 AI가 장바구니를 직접 변경하게 만들지 않습니다.
- 현재는 메뉴 커밋 후 내부 재색인 엔드포인트를 한 번 호출하고 실패를 로그로만 남깁니다.
  메뉴 트랜잭션은 롤백하지 않으며, 운영 전 Spring에 outbox/작업 큐와 백오프 재시도를 추가해야 합니다.
- P1에서 `menuIds`는 트리거 메타데이터로 취급합니다. AI가 현재 매장의 전체 스냅샷을 새로고침하므로
  재전달 시 부분 리비전 유실 없이 멱등 처리할 수 있지만, 현재 Spring 전달 자체는 내구성이 없습니다.

## 클라우드

- WSS `/ai/ws`를 FastAPI로 라우팅하고 WebSocket Upgrade 헤더를 보존합니다.
- Spring/AI에 각각 같은 키 쌍의 개인 키/공개 키를 주입하고 `RS256`, `silki-be`, `ai-ws`를
  동일하게 설정합니다. 개인 키를 AI, FE, 로그 또는 이미지에 넣지 않습니다.
- `/ai/internal/*`을 Spring-AI 간 네트워크 트래픽으로 제한합니다.
- pgvector를 활성화합니다. AI에는 Spring 메뉴 호환 뷰의 읽기 전용 권한과 AI 임베딩/리비전 테이블의 읽기/쓰기 권한을 부여합니다.
- TCP 50051의 CLOVA Speech 및 HTTPS의 Gemini로 나가는 통신을 허용합니다.
- `jhgan/ko-sroberta-multitask`를 이미지에 포함하거나 Hugging Face 다운로드 이그레스를 허용하고 영구 모델 캐시를 연결합니다. 준비 상태 확인 뒤 느린 첫 요청 모델 다운로드가 발생하지 않도록 프로덕션에서 `SILKI_AI_EMBEDDING_PRELOAD=true`를 설정합니다.
- EC2는 CPU 인스턴스를 사용합니다. PyTorch는 CPU 전용 인덱스에서 설치되며 GPU 드라이버나 가속기 런타임을 설치하지 않습니다.
- 플랫폼 시크릿 매니저에서 CLOVA, Gemini, 내부 API, 데이터베이스, JWT 검증 시크릿을 주입합니다.
- ALB/프록시 유휴 타임아웃은 최소 180초로 설정합니다. 애플리케이션 기본 유휴 타임아웃 120초보다 길게 유지하고, 활성 소켓·단계별 지연 시간·제공자 장애·저하 폴백을 모니터링합니다.

원시 오디오는 메모리에서 처리하며 저장하지 않습니다.

## 연동 전 확정할 API 계약 결정

- JWT 공개 키 전달/교체 방식과 토큰 TTL. 알고리즘/발급자/대상은 각각
  `RS256`, `silki-be`, `ai-ws`로 고정합니다.
- `docs/api-contract.md`의 camelCase JSON 스키마
- PCM 리틀 엔디언 프레이밍과 FE AudioWorklet/리샘플링 구현
- Spring에서 정수 `basedOnCartVersion`을 증가시키는 규칙
- 권한 있는 메뉴 관계/열 매핑과 단조 증가하는 `sourceRevision`
- 후보 필드: `menuId`, `name`, `description`, `score`, `matchedAttributes`
- 발화 단위 `quantity`(1~99, 기본 1). 메뉴 옵션과 장바구니 반영은 FE/Spring에서 확인
- 공통 오류 처리, 재시도 동작, 오래된 장바구니 UX
- 재연결 동작: 항상 새 토큰/세션을 요청하고 최신 전체 장바구니 컨텍스트를 다시 전송

## P1 (MVP)

- 직접 연결하는 FE-FastAPI WSS 및 CLOVA Speech gRPC 스트리밍
- Spring 서명 짧은 수명 AI 액세스 토큰 검증
- `sessionId`/`turnId` 상관관계 및 애플리케이션 소유 Turn Manager
- 일반 무음 1.5초 및 불완전한 발화에 대한 2.5초 임곗값
- 결정론적 저하 폴백이 포함된 Gemini 구조화 쿼리 정제
- 매장 격리 PostgreSQL/pgvector 검색과 대화 화면용 최대 2개 후보
- 강한 속성 필터가 0건이면 속성 없는 의미 검색을 한 번 재시도
- 전달된 Spring 재색인 요청에 대한 AI 측 리비전 멱등성
- Spring에서 후보 확인 및 권한 있는 장바구니/메뉴 재검증

## P2 (추후)

- Redis 일회성 `jti` 소진 및 토큰 재사용 방지
- DB 읽기가 적합하지 않을 경우 메뉴 수준 페이로드 업서트/삭제 동기화
- 개인화된 VAD 및 더 정교한 문장 완성 로직
- 자동화된 임곗값/속성 가중치 조정 및 확장된 평가 데이터 세트
- 수평 확장을 위한 공유 세션 메타데이터와 상세 대시보드
- 폐기된 MySQL/Qdrant/주문 API 잔여 코드의 물리적 삭제

## Spring 메뉴 원본 계약

Spring의 현재 Flyway V8 마이그레이션이 만드는 `public.ai_menu_source`를 기본값으로 사용하고
`SILKI_AI_MENU_SOURCE_TABLE=public.ai_menu_source`를 배포 환경에도 명시합니다. 다른 관계를
사용하려면 같은 열 계약을 노출해야 하며 AI 계정에는 `SELECT`만 부여합니다. 배포 후에는
[`spring-menu-contract.sql`](spring-menu-contract.sql)의 읽기 전용 검증 쿼리를 AI 계정으로 실행합니다.

Spring/Hibernate에서 PostgreSQL `TEXT[]`를 직접 매핑할 때는 Hibernate 6의
`@JdbcTypeCode(SqlTypes.ARRAY)` 같은 배열 매핑을 사용합니다. 어렵다면 Spring이 관리하는
호환 뷰에서 `flavor_tags`를 `TEXT[]`로 변환해도 됩니다. 관리 화면의 선택지는 DDL과 동일한
표준 값만 보내야 합니다.

현재 제공된 `메뉴_목록_20개.xlsx`에는 번호와 메뉴명만 있습니다. 이 두 열만 적재하지 말고,
재색인 전에 위 계약의 설명·카테고리·온도·당도·카페인·맛 태그·판매 가능 여부를 Spring에서
채워야 합니다. 값이 아직 정해지지 않은 선택 속성은 임의 문자열 대신 `NULL`을 사용합니다.
