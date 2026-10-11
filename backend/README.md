# Silko BE API

FE DTO 이름, 순수 JavaScript용 JSDoc 타입, API별 요청·응답과 `fetch` 예시는 [FE API DTO 및 요청 가이드](docs/FE_API_GUIDE.md)를 참고합니다.
주문 실시간 알림의 이벤트 명세, FE 연결, 재연결 및 Postman 테스트는 [주문 SSE 가이드](docs/SSE_GUIDE.md)를 참고합니다.

## AI 음성 세션 액세스 토큰

고객 주문 세션을 만든 뒤 아래 공개 API에서 AI WebSocket의 `session.start.accessToken`에 사용할
단기 RS256 JWT를 발급합니다. 요청 본문은 없으며 `storeId`는 클라이언트 값이 아니라 DB의 주문 세션에서만 결정합니다.

```http
POST /api/v1/order-sessions/{sessionId}/ai-token
```

```json
{
  "accessToken": "<RS256 JWT>",
  "expiresAt": "2026-08-19T13:00:00Z"
}
```

발급하려면 주문 세션이 존재하고 `ACTIVE`이며 만료되지 않아야 합니다. 응답에는
`Cache-Control: no-store`와 `Pragma: no-cache`가 포함됩니다. JWT는 FE 메모리에서만 유지하고
`localStorage`, `sessionStorage`, 로그에 저장하지 않습니다. 재연결할 때는 새 토큰을 발급합니다.

JWT 계약은 다음과 같습니다.

| 항목 | 값 |
| --- | --- |
| 서명 알고리즘 | `RS256` 고정 |
| `sub` | DB의 주문 세션 ID |
| `storeId` | DB 주문 세션의 매장 ID |
| `iss` | 기본 `silki-be` |
| `aud` | 기본 `ai-ws` |
| 그 외 필수 claim | `iat`, `exp`, `jti` |
| 만료 시각 | `min(발급 시각 + AI_JWT_TTL, 주문 세션 만료 시각)` |

Spring 배포 환경에는 다음 값을 설정합니다.

| 환경 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `AI_JWT_PRIVATE_KEY` | 없음(필수) | RSA 2048비트 이상의 PKCS#8 PEM 개인키. Secret Manager에서 주입하며 `\n` 이스케이프도 허용 |
| `AI_JWT_ISSUER` | `silki-be` | AI의 `SILKI_AI_JWT_ISSUER`와 일치 |
| `AI_JWT_AUDIENCE` | `ai-ws` | AI의 `SILKI_AI_JWT_AUDIENCE`와 일치 |
| `AI_JWT_TTL` | `2m` | 1분 이상 3분 이하의 단기 토큰 TTL |

개인키가 없거나 PKCS#8 형식이 아니거나 RSA 키가 2048비트 미만이면 애플리케이션이 fail-closed로 시작에 실패합니다.
개발 키 쌍은 다음처럼 만들 수 있습니다. 개인키는 Spring에만, 공개키는 AI의
`SILKI_AI_JWT_PUBLIC_KEY`에만 배포합니다.

```bash
openssl genpkey -algorithm RSA -pkeyopt rsa_keygen_bits:2048 -out ai-jwt-private.pem
openssl pkey -in ai-jwt-private.pem -pubout -out ai-jwt-public.pem
```

## AI 메뉴 재색인 연동

메뉴 생성·수정·삭제·품절 상태 변경이 커밋되면 Spring이 AI 내부 API를 호출합니다.
재색인 실패는 이미 커밋된 메뉴 변경을 롤백하지 않으며 경고 로그로 남습니다. AI는 요청을 받을 때 해당 매장의
현재 전체 메뉴를 다시 읽으므로 다음 메뉴 변경 요청으로 누락된 이전 변경도 함께 반영됩니다.

```http
POST {AI_BASE_URL}/ai/internal/v1/stores/{storeId}/reindex
X-Internal-API-Key: {AI_INTERNAL_API_KEY}
Content-Type: application/json
```

```json
{
  "menuIds": ["변경된-menuId"],
  "sourceRevision": 1,
  "reason": "menu.created"
}
```

Spring 배포 환경 변수:

| 환경 변수 | 기본값 | 용도 |
| --- | --- | --- |
| `AI_REINDEX_ENABLED` | `false` | 메뉴 변경 후 AI 재색인 호출 활성화 |
| `AI_BASE_URL` | `http://localhost:8000` | 내부 AI 서버 기본 URL |
| `AI_INTERNAL_API_KEY` | 빈 값 | AI의 `SILKI_AI_INTERNAL_API_KEY`와 동일한 내부 키 |
| `AI_CONNECT_TIMEOUT` | `1s` | AI 연결 제한 시간 |
| `AI_REINDEX_REQUEST_TIMEOUT` | `3s` | 재색인 요청 전체 제한 시간 |

AI 서버는 Spring과 같은 PostgreSQL의 `public.ai_menu_source` 뷰를 읽도록
`SILKI_AI_MENU_SOURCE_TABLE=public.ai_menu_source`를 설정해야 합니다. AI DB 계정에는 이 뷰의 `SELECT` 권한과
AI 소유 임베딩 테이블의 읽기·쓰기 권한만 부여합니다.

기존 메뉴가 이미 적재된 최초 배포에서는 AI 내부 재색인 API를 `menuIds=[]`, `sourceRevision=0`,
`reason=initial.index`로 한 번 호출해 전체 메뉴 임베딩을 생성합니다. 이후 Spring이 발생시키는 리비전은 1부터 시작합니다.

## 인증과 권한

- 관리자 API는 `JSESSIONID` 쿠키를 사용하는 세션 인증 방식입니다.
- 로그인 이후 관리자 요청에는 세션 쿠키를 포함해야 합니다. 브라우저 `fetch` 사용 시 `credentials: "include"`를 설정합니다.
- 인증되지 않은 관리자의 요청은 `401 UNAUTHORIZED`를 반환합니다.
- 가게 단위 관리자 API는 로그인한 관리자와 가게의 매핑도 확인합니다. 담당하지 않는 가게는 `404 STORE_NOT_FOUND`를 반환합니다.
- CloudFront가 HTTPS를 종료하고 EC2 원본에는 HTTP로 연결하는 운영 환경에서는
  `SERVER_SERVLET_SESSION_COOKIE_SECURE=true`를 반드시 설정합니다. 이 값은 `JSESSIONID`와
  자동 로그인 쿠키에 함께 적용됩니다.

## FE에서 준비할 값

| 값 | FE에서 가져오는 방법 | 사용 규칙 |
| --- | --- | --- |
| `JSESSIONID` | 로그인 응답의 `Set-Cookie`로 브라우저가 자동 저장 | 직접 생성하거나 읽지 않습니다. 로그인과 모든 관리자 `fetch` 요청에 `credentials: "include"`를 사용합니다. |
| `storeId` | 관리자는 `GET /api/v1/admin/stores` 응답에서 사용 | 공개 가게 목록 API는 없으므로 고객 화면은 URL, QR 또는 FE 설정으로 `storeId`를 전달받아야 합니다. |
| `menuId` | 관리자 또는 공개 메뉴 조회 응답의 `id` | 주문 항목의 `items[].menuId`와 메뉴 수정·삭제 경로에 사용합니다. |
| `orderId` | 주문 생성 응답의 `id` | 주문 상태 조회와 주문 SSE 연결에 사용합니다. |
| `Idempotency-Key` | 주문 시도마다 `crypto.randomUUID()`로 생성 | 같은 주문을 재시도할 때는 같은 값을 재사용합니다. 주문 내용이 바뀌거나 새 주문이면 새 값을 생성합니다. 최대 100자입니다. |
| `imageKey` | 메뉴 이미지 업로드 응답의 `imageKey` | 업로드 응답값을 그대로 사용합니다. `imageUrl`이나 임의 문자열을 넣지 않으며 이미지가 없으면 `null`로 보냅니다. |
| `category` | FE 카테고리 선택값 | 메뉴 조회·등록·수정 시 필수이며 `COFFEE`, `BEVERAGE`, `TEA` 중 하나를 보냅니다. |
| `status` | FE 상태 변경 UI의 선택값 | 가게 상태는 `OPEN`/`CLOSED`, 주문 상태는 정해진 순서, 메뉴 판매 상태는 `AVAILABLE`/`SOLD_OUT`을 사용합니다. |
| `page`, `size` | FE 페이지 상태 | 생략 시 각각 `0`, `20`이며 `size`는 최대 `100`입니다. |

관리자 요청 예시:

```js
await fetch(`${API_URL}/api/v1/admin/stores`, {
  credentials: "include",
});
```

### FE 자동 로그인 처리

로그인 화면의 자동 로그인 체크값을 `rememberMe`로 전달합니다. `true`이면 세션이 끝나도 자동 로그인을 복원할 수 있는 쿠키가 함께 발급되며, 기본 유효기간은 14일입니다. `false`이면 현재 세션만 사용합니다.

```js
await fetch(`${API_URL}/api/v1/admin/auth/login`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({ email, password, rememberMe }),
});
```

쿠키는 브라우저가 관리하므로 FE의 `localStorage`나 `sessionStorage`에 인증 토큰을 저장하지 않습니다. 앱 시작 시 담당 가게 API로 로그인 상태를 확인합니다. 응답이 `401`이면 로그인 화면으로 이동합니다.

```js
const response = await fetch(`${API_URL}/api/v1/admin/stores`, {
  credentials: "include",
});

if (response.status === 401) {
  // 로그인 화면으로 이동
}
```

로그아웃할 때는 세션과 자동 로그인 토큰을 함께 폐기합니다.

```js
await fetch(`${API_URL}/api/v1/admin/auth/logout`, {
  method: "POST",
  credentials: "include",
});
```

주문 생성 시에는 요청 전에 키를 한 번 만들고, 네트워크 재시도에도 같은 값을 사용합니다.

```js
const idempotencyKey = crypto.randomUUID();

await fetch(`${API_URL}/api/v1/stores/${storeId}/orders`, {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Idempotency-Key": idempotencyKey,
  },
  body: JSON.stringify({ items }),
});
```

관리자 SSE는 세션 쿠키를 포함해야 하므로 `new EventSource(url, { withCredentials: true })`로 연결합니다. 고객 주문 SSE는 공개 API라 인증 쿠키가 필요하지 않습니다.

## 음료 메뉴와 주문 옵션

메뉴 등록·수정 시 주문 가능한 온도, 기본 당도, 카페인 유무, 샷 추가 가능 여부를 함께 보냅니다. `availableTemperatures`에는 `HOT`, `ICE` 중 하나 이상이 필요합니다.

```json
{
  "category": "COFFEE",
  "name": "아메리카노",
  "description": "고소한 원두",
  "price": 4500,
  "imageKey": null,
  "availableTemperatures": ["HOT", "ICE"],
  "defaultSweetness": "MEDIUM",
  "caffeinated": true,
  "extraShotAvailable": false
}
```

메뉴 조회 응답의 `availableOptions`는 FE가 선택 UI에 사용할 수 있는 `type`, `code`, `name`, `additionalPrice`를 제공합니다. 당도 옵션에는 메뉴 기본 당도로 계산한 `finalSweetness`도 포함됩니다. `extraShotAvailable=false`이면 샷 옵션은 응답에서 제외됩니다.

| 옵션 | 코드 | 이름 | 추가 금액 |
| --- | --- | --- | ---: |
| 온도 | `HOT` | 따뜻하게 | 0 |
| 온도 | `ICE` | 차갑게 | 0 |
| 사이즈 | `REGULAR` | 레귤러 | 0 |
| 사이즈 | `LARGE` | 라지 | 500 |
| 샷 추가 | `NONE` | 추가 안 함 | 0 |
| 샷 추가 | `SHOT_1` | 샷 1회 추가 | 500 |
| 샷 추가 | `SHOT_2` | 샷 2회 추가 | 1,000 |
| 당도 | `LESS` | 덜 달게 | 0 |
| 당도 | `NORMAL` | 보통 | 0 |
| 당도 | `MORE` | 더 달게 | 0 |

당도 요청은 메뉴의 `defaultSweetness`를 기준으로 계산됩니다. 요청을 생략하면 `NORMAL`로 처리합니다.

| 기본 당도 | `LESS` | `NORMAL` 또는 생략 | `MORE` |
| --- | --- | --- | --- |
| `LOW` | `VERY_LOW` | `LOW` | `MEDIUM` |
| `MEDIUM` | `LOW` | `MEDIUM` | `HIGH` |
| `HIGH` | `MEDIUM` | `HIGH` | `VERY_HIGH` |

주문 항목의 `options.temperature`는 필수이고 나머지는 생략할 수 있습니다. 생략 기본값은 `size=REGULAR`, `extraShot=NONE`, `sweetness=NORMAL`입니다. 같은 메뉴를 서로 다른 옵션으로 주문하려면 별도 항목으로 보냅니다.

```json
{
  "items": [
    {
      "menuId": "00000000-0000-0000-0000-000000000000",
      "quantity": 2,
      "options": {
        "temperature": "ICE",
        "size": "LARGE",
        "extraShot": "SHOT_1",
        "sweetness": "LESS"
      }
    }
  ]
}
```

주문 생성 응답, 관리자 주문 목록, 신규 주문 SSE의 각 주문 항목에는 서버가 계산한 가격과 옵션 스냅샷이 포함됩니다.

```json
{
  "menuName": "아메리카노",
  "quantity": 2,
  "basePrice": 4500,
  "unitPrice": 5500,
  "subtotal": 11000,
  "options": [
    { "type": "TEMPERATURE", "code": "ICE", "name": "차갑게", "additionalPrice": 0 },
    { "type": "SIZE", "code": "LARGE", "name": "라지", "additionalPrice": 500 },
    { "type": "EXTRA_SHOT", "code": "SHOT_1", "name": "샷 1회 추가", "additionalPrice": 500 },
    { "type": "SWEETNESS", "code": "LESS", "name": "덜 달게", "additionalPrice": 0 }
  ],
  "finalSweetness": "LOW"
}
```

## 컨트롤러별 API

### AuthController

관리자 로그인을 처리합니다.

| API | 요청 명세 |
| --- | --- |
| `POST /api/v1/admin/auth/login` | **용도:** 관리자 로그인 및 세션 생성<br>**접근:** 공개<br>**헤더:** `Content-Type: application/json`<br>**입력:** JSON `email`, `password`; 선택 `rememberMe`(기본 `false`) |
| `POST /api/v1/admin/auth/logout` | **용도:** 세션과 자동 로그인 토큰 폐기<br>**접근:** 로그인 사용자<br>**헤더:** 세션 쿠키 |

### StoreController

로그인한 관리자의 담당 가게와 운영 상태를 관리합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/admin/stores` | **용도:** 담당 가게 목록 조회<br>**접근:** 세션 인증<br>**헤더:** 세션 쿠키<br>**입력:** 없음 |
| `POST /api/v1/admin/stores` | **용도:** 가게 등록<br>**접근:** 세션 인증<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** JSON `name` |
| `GET /api/v1/admin/stores/{storeId}/status` | **용도:** 가게 운영 상태 조회<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키<br>**입력:** Path `storeId` |
| `PATCH /api/v1/admin/stores/{storeId}/status` | **용도:** 가게 운영 상태 변경<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** Path `storeId`, JSON `status` |

### PublicStoreController

고객에게 가게 영업 상태와 주문 가능 여부를 공개합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/stores/{storeId}/order-context` | **용도:** 가게 정보, 영업 상태, 주문 가능 여부와 안내 문구 조회<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `storeId` |
| `GET /api/v1/stores/{storeId}/status` | **용도:** 가게 영업 상태 조회<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `storeId` |

### MenuController

담당 가게의 메뉴와 메뉴 이미지를 관리합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/admin/stores/{storeId}/menus` | **용도:** 카테고리별 메뉴 목록 조회<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키<br>**입력:** Path `storeId`, Query `category`; 선택 `page`(기본 0), `size`(기본 20, 최대 100) |
| `POST /api/v1/admin/stores/{storeId}/menus` | **용도:** 메뉴 등록<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** Path `storeId`, JSON `category`, `name`, `price`, `availableTemperatures`, `defaultSweetness`, `caffeinated`, `extraShotAvailable`; 선택 `description`, `imageKey` |
| `PATCH /api/v1/admin/stores/{storeId}/menus/{menuId}` | **용도:** 메뉴 정보 수정<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** Path `storeId`, `menuId`, JSON `category`, `name`, `price`, `availableTemperatures`, `defaultSweetness`, `caffeinated`, `extraShotAvailable`; 선택 `description`, `imageKey` |
| `DELETE /api/v1/admin/stores/{storeId}/menus/{menuId}` | **용도:** 메뉴 및 연결 이미지 삭제<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키<br>**입력:** Path `storeId`, `menuId` |
| `PATCH /api/v1/admin/stores/{storeId}/menus/{menuId}/sales-status` | **용도:** 메뉴 판매 상태 변경<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** Path `storeId`, `menuId`, JSON `salesStatus` |
| `POST /api/v1/admin/stores/{storeId}/menus/images` | **용도:** 메뉴 이미지 업로드<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: multipart/form-data`(브라우저 자동 설정)<br>**입력:** 파일 필드 `file` |

이미지는 JPEG, PNG, WebP 형식과 최대 5MB를 지원합니다. 업로드 응답의 `imageKey`를 메뉴 등록 또는 수정 요청에 사용합니다. `FormData` 업로드 시 `Content-Type`은 boundary를 포함하도록 브라우저가 생성하므로 FE에서 직접 지정하지 않습니다.

### PublicMenuController

고객에게 가게 메뉴를 공개합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/stores/{storeId}/menus` | **용도:** 카테고리별 메뉴 설명과 주문 옵션 목록 조회<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `storeId`, Query `category`; 선택 `page`(기본 0), `size`(기본 20, 최대 100) |
| `GET /api/v1/stores/{storeId}/menus/{menuId}` | **용도:** AI 후보 메뉴의 현재 가격·판매 상태·옵션 UUID 단건 재검증<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `storeId`, `menuId`; 다른 매장 메뉴도 `404 MENU_NOT_FOUND` |

옵션 그룹은 `requiresSelection`과 `autoSelectedOptionId`를 반환합니다. FE와 AI는 기본 옵션 또는 단일 선택지가 있으면 자동 적용하고, `requiresSelection=true`인 그룹만 사용자에게 질문합니다.
AI 후보의 이름과 가격은 표시용이며, 장바구니 반영 전 이 단건 API 응답을 권한 데이터로 사용합니다.

### OrderController

고객 주문 생성과 주문 상태 확인을 처리합니다.

| API | 요청 명세 |
| --- | --- |
| `POST /api/v1/stores/{storeId}/orders` | **용도:** 고객 주문 생성<br>**접근:** 공개<br>**헤더:** `Content-Type: application/json`, `Idempotency-Key: {주문 시도별 UUID}`<br>**입력:** Path `storeId`, JSON `items[].menuId`, `items[].quantity`, `items[].options.temperature`; 선택 `size`, `extraShot`, `sweetness` |
| `GET /api/v1/orders/{orderId}` | **용도:** 주문 상세, 현재 상태 및 픽업 안내 조회<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `orderId` |
| `GET /api/v1/orders/{orderId}/stream` | **용도:** 주문 상태 및 픽업 준비 SSE 구독<br>**접근:** 공개<br>**헤더:** `Accept: text/event-stream`(EventSource 자동 설정)<br>**입력:** Path `orderId` |

### OrderSessionController

영업 중인 가게에서 고객 주문 세션을 시작합니다. 생성된 `cartVersion`은 AI 추천과 장바구니 동기화 기준으로 사용합니다.

| 메서드 | 경로 | 접근 | 용도 | 필수 입력 |
| --- | --- | --- | --- | --- |
| `POST` | `/api/v1/stores/{storeId}/order-sessions` | 공개 | 고객 주문 세션 생성 | Path: `storeId` |
| `POST` | `/api/v1/order-sessions/{sessionId}/ai-token` | 공개 | AI WebSocket용 단기 RS256 토큰 발급 | Path: `sessionId` |
| `PATCH` | `/api/v1/order-sessions/{sessionId}/fulfillment` | 공개 | 매장/포장 선택 | Header: `If-Match`, JSON: `fulfillmentType` |

AI가 매장 이용 여부를 질문한 뒤 FE는 `fulfillmentType`에 `DINE_IN` 또는 `TAKEOUT`을 전달합니다.
선택이 변경되면 `cartVersion`이 1 증가하며, 같은 값을 다시 선택하면 현재 버전을 그대로 반환합니다.

### CartController

활성 주문 세션의 장바구니 항목, 선택 옵션, 권한 있는 가격 합계와 현재 `cartVersion`을 조회합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/order-sessions/{sessionId}/cart` | **용도:** 장바구니 조회<br>**접근:** 공개<br>**헤더:** 없음<br>**입력:** Path `sessionId` |
| `POST /api/v1/order-sessions/{sessionId}/cart/items` | **용도:** 메뉴와 선택 옵션을 장바구니에 추가<br>**접근:** 공개<br>**헤더:** `Content-Type: application/json`, `If-Match: {현재 cartVersion}`<br>**입력:** Path `sessionId`, JSON `menuId`, `quantity`, `optionValueIds` |
| `PATCH /api/v1/order-sessions/{sessionId}/cart/items/{cartItemId}` | **용도:** 장바구니 항목의 수량과 옵션 교체<br>**접근:** 공개<br>**헤더:** `Content-Type: application/json`, `If-Match: {현재 cartVersion}`<br>**입력:** Path `sessionId`, `cartItemId`, JSON `quantity`, `optionValueIds` |
| `DELETE /api/v1/order-sessions/{sessionId}/cart/items/{cartItemId}` | **용도:** 장바구니 항목 삭제<br>**접근:** 공개<br>**헤더:** `If-Match: {현재 cartVersion}`<br>**입력:** Path `sessionId`, `cartItemId` |

장바구니 변경 요청은 조회 응답의 `cartVersion`을 `If-Match` 헤더로 전달합니다. 기본 옵션 또는 선택지가 하나인 옵션은 자동 적용되며, 변경 성공 후 `cartVersion`이 1 증가합니다.

### OrderPreviewController

사용자가 AI의 주문 확인 질문에 동의하기 전에 현재 장바구니를 서버 기준으로 최종 검증합니다.

| API | 요청 명세 |
| --- | --- |
| `POST /api/v1/order-sessions/{sessionId}/preview` | **용도:** 주문 미리보기 및 최종 검증<br>**접근:** 공개<br>**헤더:** `If-Match: {현재 cartVersion}`<br>**입력:** Path `sessionId` |

영업 상태, 활성 세션, `cartVersion`, 매장/포장 선택, 빈 장바구니, 메뉴별 합산 수량, 품절 및 옵션 유효성을
검증한 뒤 현재 메뉴·옵션 가격으로 합계를 계산합니다. 미리보기는 주문이나 재고를 예약하지 않으므로 실제 주문 생성 시
동일한 검증을 다시 수행해야 합니다.

### CheckoutController

미리보기에서 확인한 주문 세션과 장바구니로 카운터 결제 주문을 생성합니다. 별도 PG 결제는 수행하지 않습니다.

| API | 요청 명세 |
| --- | --- |
| `POST /api/v1/order-sessions/{sessionId}/orders` | **용도:** 카운터 결제 주문 생성<br>**접근:** 공개<br>**헤더:** `If-Match: {현재 cartVersion}`, `Idempotency-Key: {주문 시도별 UUID}`<br>**입력:** Path `sessionId` |

성공 시 주문 상태는 `RECEIVED`, 결제 방식은 `PAY_AT_COUNTER`이며 주문 세션은 `ORDERED`로 종료됩니다.
동일한 `Idempotency-Key` 재요청은 기존 주문을 반환하고, 주문 생성 이벤트는 관리자 매장 SSE에 전달됩니다.

### AdminOrderController

담당 가게의 주문 처리와 실시간 주문 알림을 관리합니다.

| API | 요청 명세 |
| --- | --- |
| `GET /api/v1/admin/stores/{storeId}/orders` | **용도:** 가게 주문 목록 최신순 페이지 조회<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키<br>**입력:** Path `storeId`; 선택 Query `page`(기본 0), `size`(기본 20, 최대 100)<br>**응답:** `content`, `page`, `size`, `totalElements`, `totalPages`, `first`, `last` |
| `PATCH /api/v1/admin/stores/{storeId}/orders/{orderId}/status` | **용도:** 주문 상태 변경<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Content-Type: application/json`<br>**입력:** Path `storeId`, `orderId`, JSON `status` |
| `GET /api/v1/admin/stores/{storeId}/orders/stream` | **용도:** 신규 주문 SSE 구독<br>**접근:** 세션 인증 및 가게 권한<br>**헤더:** 세션 쿠키, `Accept: text/event-stream`(EventSource 자동 설정)<br>**입력:** Path `storeId` |

## API 공개 범위

### 공개 API 및 리소스

| 메서드 | 경로 | 용도 |
| --- | --- | --- |
| `POST` | `/api/v1/admin/auth/login` | 관리자 로그인 |
| `POST` | `/api/v1/stores/{storeId}/orders` | 고객 주문 생성 |
| `POST` | `/api/v1/stores/{storeId}/order-sessions` | 고객 주문 세션 생성 |
| `POST` | `/api/v1/order-sessions/{sessionId}/ai-token` | AI WebSocket용 단기 액세스 토큰 발급 |
| `PATCH` | `/api/v1/order-sessions/{sessionId}/fulfillment` | 고객 매장/포장 선택 |
| `GET` | `/api/v1/stores/{storeId}/order-context` | 고객 가게 운영 상태 조회 |
| `GET` | `/api/v1/stores/{storeId}/menus` | 고객 메뉴 조회 |
| `GET` | `/api/v1/stores/{storeId}/menus/{menuId}` | AI 후보 메뉴 및 주문 옵션 단건 재검증 |
| `GET` | `/api/v1/stores/{storeId}/status` | 가게 영업 상태 조회 |
| `GET` | `/api/v1/order-sessions/{sessionId}/cart` | 고객 장바구니 조회 |
| `POST` | `/api/v1/order-sessions/{sessionId}/cart/items` | 고객 장바구니에 메뉴 추가 |
| `PATCH` | `/api/v1/order-sessions/{sessionId}/cart/items/{cartItemId}` | 고객 장바구니 수량 및 옵션 수정 |
| `DELETE` | `/api/v1/order-sessions/{sessionId}/cart/items/{cartItemId}` | 고객 장바구니 항목 삭제 |
| `POST` | `/api/v1/order-sessions/{sessionId}/preview` | 고객 주문 미리보기 및 최종 검증 |
| `POST` | `/api/v1/order-sessions/{sessionId}/orders` | 카운터 결제 주문 생성 |
| `GET` | `/api/v1/orders/{orderId}` | 주문 상세, 현재 상태 및 픽업 안내 조회 |
| `GET` | `/api/v1/orders/{orderId}/stream` | 주문 상태 및 픽업 준비 SSE 구독 |
| `GET` | `/uploads/**` | 업로드 이미지 조회 |
| 전체 | `/swagger-ui/**`, `/swagger-ui.html`, `/v3/api-docs/**` | Swagger 및 OpenAPI 문서 |

### 인증 필요 API

`POST /api/v1/admin/auth/login`을 제외한 모든 `/api/v1/admin/**` API는 로그인이 필요합니다. 이 중 `{storeId}`가 포함된 API는 로그인한 관리자가 해당 가게를 담당하는지도 확인합니다.

## 주요 상태 값

| 타입 | 값 |
| --- | --- |
| `MenuCategory` | `COFFEE`, `BEVERAGE`, `TEA` |
| `SalesStatus` | `AVAILABLE`, `SOLD_OUT` |
| `Temperature` | `HOT`, `ICE` |
| `DefaultSweetness` | `LOW`, `MEDIUM`, `HIGH` |
| `FinalSweetness` | `VERY_LOW`, `LOW`, `MEDIUM`, `HIGH`, `VERY_HIGH` |
| `OperatingStatus` | `OPEN`, `CLOSED` |
| `OrderStatus` | `RECEIVED`, `PREPARING`, `COMPLETED` |
| `FulfillmentType` | `DINE_IN`, `TAKEOUT` |
| `PaymentMethod` | `PAY_AT_COUNTER` |

주문 상태는 `RECEIVED` → `PREPARING` → `COMPLETED` 순서로만 변경할 수 있습니다.
고객 상태 응답은 `pickupReady`, `message`, `updatedAt`을 포함합니다. `COMPLETED` 변경 시 고객 SSE에
`ORDER_STATUS_CHANGED` 다음 `PICKUP_READY` 이벤트를 전송하고 연결을 종료합니다.

관리자가 메뉴를 생성하면 온도·사이즈·당도 기본 옵션이 함께 생성되고, 카페인 메뉴에는 샷 추가 옵션도
생성됩니다. 기존 메뉴는 Flyway V11에서 같은 규칙으로 보완됩니다. 고객 장바구니는 메뉴 응답의
`options[].values[].id`를 `optionValueIds`로 사용합니다.
