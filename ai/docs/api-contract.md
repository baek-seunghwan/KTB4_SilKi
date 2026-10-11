# API 계약

WebSocket 경계의 JSON 필드는 camelCase를 사용합니다. 오디오는 바이너리 프레임을 사용합니다.
알 수 없는 메시지 유형에는 복구 가능한 `error` 이벤트를 반환합니다.

## 인증 및 세션 시작

Spring은 `RS256`으로만 서명하고 `sub`, `storeId`, `aud`, `iss`, `iat`, `exp`, `jti`를
포함하는 짧은 수명의 JWT를 발급합니다. `sub`는 주문 세션 UUID, `storeId`는 Spring이
주문 세션에서 조회한 매장 UUID이며 클라이언트 입력을 사용하지 않습니다.
`/ai/ws`를 연 뒤 클라이언트는 3초 이내에 다음 메시지를 보내야 합니다.

```json
{
  "type": "session.start",
  "accessToken": "<signed JWT>",
  "basedOnCartVersion": 12,
  "cartItems": [],
  "capabilities": ["dialog.v1"]
}
```

FastAPI는 `alg=RS256`, `iss=silki-be`, 단일 `aud=ai-ws`, 서명, 필수 claim, 만료와 최대
수명을 검증하고 토큰의 `sub=orderSessionId`와 `storeId`를 연결에 바인딩한 뒤 새 `sessionId`를
생성합니다. 클라이언트는 다음 응답의 두 claim 값을 현재 주문 세션과 비교해야 합니다.

```json
{
  "type": "session.ready",
  "sessionId": "<AI 연결 UUID>",
  "orderSessionId": "<JWT sub>",
  "storeId": "<JWT storeId>",
  "capabilities": ["dialog.v1"]
}
```

인증 실패 시 `authentication_failed`를 전송하고 4401로 닫으며,
검증 전에는 CLOVA 스트림을 만들지 않습니다. 재연결할 때는 새 토큰과 새 WebSocket을 사용해야 합니다.
Spring은 서명 개인 키를 보관하고 AI에는 RSA 공개 검증 키만 전달합니다.
Redis 기반 일회성 `jti` 소진은 P2입니다.

## 오디오 및 턴 이벤트

오디오 프레임은 원시 PCM입니다. 16,000 Hz, 모노, 부호 있는 16비트 리틀 엔디언을 사용합니다.
권장 프레임 크기는 20ms(640바이트)이며, 더 큰 청크는 내부에서 다시 프레이밍됩니다.

```json
{"type":"turn.started","sessionId":"...","turnId":"...","basedOnCartVersion":12}
{"type":"stt.partial","sessionId":"...","turnId":"...","text":"차갑고"}
{"type":"turn.final","sessionId":"...","turnId":"...","text":"차갑고 안 단 음료","reason":"silence"}
```

모든 비동기 턴 이벤트는 두 식별자를 모두 포함합니다. 검색 작업은 턴의 장바구니 버전 스냅샷을 캡처하므로,
느린 응답이 이후 턴에 연결될 수 없습니다.

`semanticEpd`는 CLOVA가 전사 세그먼트를 생성하도록 돕는 역할만 합니다. 확정 처리는 FastAPI의 Turn Manager가 담당합니다.
WebRTC VAD가 음성으로 판정하고 PCM16 RMS가 설정된 dBFS 임곗값 이상일 때만 음성 프레임으로 취급합니다.
일반적으로 1.5초의 무음 후 확정하며, 최신 전사문이 불완전해 보일 때는 최대 2.5초 후에 확정합니다.
잡음이 계속 음성으로 판정되더라도 비어 있지 않은 STT 문장이 기본 3초 동안 달라지지 않으면
`reason=transcript_stable_timeout`으로 확정합니다. 이 안전장치는 `SILKI_AI_TURN_TRANSCRIPT_STABLE_SECONDS=0`으로 끌 수 있습니다.
지속적인 배경음 때문에 무음 구간이 생기지 않아도 기본 15초의 최대 발화 시간에 도달하면 강제로 확정합니다.
`turn.final`을 내보내기 전에 0이 아닌 `seqId`와 `epFlag=true`로 CLOVA를 플러시합니다.

## `dialog.v1` 누적 대화

FE가 `session.start.capabilities`에 `"dialog.v1"`을 넣으면 AI는 기존 HTTP 경로나 장바구니 API를
추가하지 않고 같은 WebSocket 안에서 누적 대화를 사용합니다. 메뉴 질문에는 검색 상위 후보를
최대 2개만 넣습니다. 메뉴가 선택된 뒤 온도 답을 받으면 선택된 `menuId`를 유지하고 옵션만
갱신하며 pgvector 메뉴 검색을 다시 실행하지 않습니다.

원본 STT에 공백·문장부호 차이만 있는 실제 매장 메뉴명이 명시되면 Gemini 정제 결과보다 먼저
그 메뉴를 사용합니다. 단, 한 발화에 서로 다른 메뉴명이 둘 이상 포함되면 임의로 고르지 않고
명확화 흐름으로 돌아갑니다. 후보의 `availableTemperatures`에는 메뉴 소스가 고정한 `hot` 또는
`ice`가 포함되며, 고정 온도와 반대되는 주문은 가능한 온도 하나만 다시 질문합니다.

질문·제안·완료 이벤트는 모두 `conversationId`, `dialogId`, `revision`, `turnId`로 연결됩니다.
클라이언트는 안내 TTS 재생이 끝난 뒤 같은 상관관계로 `dialog.listen`을 보내고 PCM 전송을
재개합니다. AI는 명확화뿐 아니라 최종 제안과 장바구니 추가 완료 상태에서도 이를 허용합니다.

```json
{
  "type": "dialog.listen",
  "sessionId": "...",
  "conversationId": "...",
  "dialogId": "...",
  "revision": 4
}
```

최종 제안에서 `맞아`, `맞아요`, `네`, `응`, `그래`는 `accept`, `아니`, `아니요`,
`아니야`, `다른 거`는 `reject`가 됩니다. 장바구니 추가 완료 질문에서는 `더 주문할게`,
`응`, `네`, `추가할게`가 `continue`, `아니`, `없어`, `주문 마칠게`, `그게 다야`가
`finish`가 됩니다. AI는 아래 이벤트만 보내며 장바구니나 화면을 직접 변경하지 않습니다.

```json
{
  "type": "dialog.action",
  "sessionId": "...",
  "conversationId": "...",
  "dialogId": "...",
  "revision": 4,
  "turnId": "...",
  "action": "accept"
}
```

FE는 이 액션을 기존 `맞아요`, `아니요`, `메뉴 더 주문하기`, `주문 마치기` 버튼 핸들러와
각각 동일하게 처리해야 합니다. 알아듣지 못한 확인 답변은 검색하지 않고 같은 제안 또는 완료
질문을 새 revision으로 다시 보냅니다.

Spring 장바구니 반영 뒤 증가한 `cart.context`가 오면 다음 이벤트와 같은 상관관계의
`purpose=completion` TTS를 보냅니다.

```json
{
  "type": "dialog.completed",
  "sessionId": "...",
  "conversationId": "...",
  "dialogId": "...",
  "revision": 5,
  "turnId": "...",
  "text": "장바구니에 담았어요. 더 주문하시겠어요?",
  "ttsExpected": true
}
```

가격·판매 상태·실제 옵션 UUID 검증, 장바구니 추가, 주문 마침 화면 이동은 계속 FE와 Spring의
기존 계약이 담당합니다.

후보 응답:

```json
{
  "type": "menu.candidates",
  "sessionId": "...",
  "turnId": "...",
  "basedOnCartVersion": 12,
  "searchQuery": "차갑고 당도가 낮은 음료",
  "quantity": 2,
  "attributes": {
    "category": null,
    "temperature": "ice",
    "sweetness": "low",
    "caffeine": null,
    "flavorTags": [],
    "excludedTags": ["달콤"]
  },
  "degraded": false,
  "candidates": [
    {
      "menuId": "42",
      "name": "아이스티 제로",
      "description": "무가당 아이스티",
      "score": 0.81,
      "matchedAttributes": ["temperature", "sweetness"]
    }
  ]
}
```

`quantity`는 발화에서 추출한 메뉴 수량이며, 명시되지 않으면 1입니다. 옵션 수량이나 샷 수가 아닙니다.
UI는 `basedOnCartVersion`을 현재 권한 있는 버전과 비교하고, Spring 장바구니 API를 호출하기 전에 사용자에게 후보와 수량 확인을 받아야 합니다.

TTS 공급자가 설정된 legacy 세션에서는 AI가 `menu.candidates`를 먼저 보낸 다음, 첫 후보에
대한 짧은 한국어 안내를 비스트리밍으로 생성해 하나의 JSON 이벤트로 보냅니다.

```json
{
  "type": "tts.audio",
  "sessionId": "...",
  "turnId": "...",
  "mediaType": "audio/mpeg",
  "audioBase64": "SUQzLi4u",
  "text": "아이스티 제로 2잔을 추천드려요. 주문에 담을까요?"
}
```

클라이언트는 `audioBase64`를 디코딩한 Blob을 `mediaType`으로 재생합니다. TTS는 후보와 같은
`turnId`로 연결되며, TTS 시간 초과·HTTP 오류·빈 응답·용량 초과가 발생해도 후보 응답과
WebSocket 세션은 유지됩니다. `dialog.v1`에서는 공급자 미설정이나 실패를 상관관계가 포함된
`tts.unavailable`로 명시합니다.

장바구니 업데이트가 확정된 후에는 새로운 전체 컨텍스트를 전송합니다.

```json
{
  "type": "cart.context",
  "sessionId": "...",
  "basedOnCartVersion": 13,
  "cartItems": [{"menuId":"42","quantity":1,"optionIds":[]}]
}
```

`{"type":"session.end","sessionId":"..."}`로 정상 종료합니다.

설정된 임곗값에 도달한 후보가 없으면 AI는 동일한 `sessionId`, `turnId`, `basedOnCartVersion`,
`searchQuery`, `quantity`, `attributes`, `degraded` 필드를 포함한 `no_match`를 반환합니다.
Gemini 시간 초과, 제공자 오류 또는 잘못된 스키마는 세션 실패가 아닙니다. AI는 최종 STT와 결정론적 추출을 사용하고,
`menu.candidates` 또는 `no_match`에 `degraded=true`를 설정합니다.

`error`는 세션이 있으면 `sessionId`, 선택적 `turnId`, 기계 판독 가능한 `code`, `retryable`을 포함합니다.
계약 코드:

- `authentication_failed`, `session_start_timeout`, `protocol_error`
- `audio_format_invalid`, `clova_unavailable`, `internal_error`
- 예약된 비즈니스 신호: `gemini_degraded`, `no_match`,
  `stale_cart_context`

Gemini 저하와 빈 검색 결과는 일반적으로 별도 `error` 대신 타입이 지정된 후보/후보 없음 이벤트로 표현됩니다.
속성이 포함된 첫 검색이 0건이면 같은 임베딩과 점수 임곗값으로 속성 필터만 제거해 한 번 더 검색합니다.
두 번째 검색도 0건일 때만 `no_match`를 반환합니다.

## 재색인

Spring은 메뉴 트랜잭션이 커밋된 뒤 다음 내부 전용 엔드포인트를 호출합니다.

```http
POST /ai/internal/v1/stores/{storeId}/reindex
X-Internal-API-Key: <service secret>
Content-Type: application/json
```

```json
{
  "menuIds": ["42", "43"],
  "sourceRevision": 105,
  "reason": "menu.updated"
}
```

AI는 권한 있는 PostgreSQL 메뉴 행을 읽고 자체 임베딩 테이블만 업데이트합니다.
중복되거나 오래된 리비전은 재처리 없이 승인합니다.

P1에서 `menuIds`는 알림을 트리거한 행을 기록하지만, AI는 항상 현재 매장의 전체 스냅샷을 읽고 다시 발행합니다.
이 방식은 매장 수준 리비전 멱등성을 유지하면서 순서가 뒤바뀐 콜백으로 이전에 커밋된 메뉴 변경이 유실되는 일을 막습니다.
삭제되었거나 판매 불가가 된 행은 해당 임베딩을 삭제합니다. 현재 Spring 구현은 메뉴 트랜잭션
커밋 후 동기 호출을 한 번 수행하고, 실패하면 로그만 남기므로 메뉴 트랜잭션을 롤백하지 않습니다.
AI의 리비전 처리는 멱등하지만 전달 자체는 아직 내구성이 없습니다. 운영 전 Spring에 outbox/작업 큐와
지수 백오프 재시도를 추가해야 합니다. P2에서는 항목별 순서 의미론을 도입한 뒤 실제 메뉴 수준
페이로드 업서트/삭제 동기화를 추가할 수 있습니다.

P1 소스 관계의 기본값은 Spring Flyway가 제공하는 `public.ai_menu_source` 호환 뷰이며
다음 열을 노출해야 합니다.
배포 후 AI DB 계정으로 실행할 검증 쿼리는 [`spring-menu-contract.sql`](spring-menu-contract.sql)에 있습니다.

| 열 | 필수 의미 |
| --- | --- |
| `store_id`, `menu_id` | TEXT, UUID 또는 정수 식별자. 쌍으로서 고유해야 함 |
| `name`, `description` | 메뉴 표시/검색 텍스트 |
| `category` | null 허용 표준 카테고리 |
| `temperature` | null 허용 `ice` 또는 `hot` |
| `sweetness` | null 허용 `low`, `medium` 또는 `high` |
| `caffeine` | null 허용 `none`, `low` 또는 `normal` |
| `flavor_tags` | `TEXT[]` |
| `is_available` | boolean 판매 가능 여부 |

AI에는 이 관계에 대한 `SELECT` 권한만, `ai.menu_embeddings`와 `ai.reindex_state`에는 읽기/쓰기 권한만 필요합니다.
가격과 재고는 의도적으로 후보 계약에 복사하지 않으며, Spring이 장바구니 업데이트 시 다시 검증합니다.
