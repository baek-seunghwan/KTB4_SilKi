# FE API DTO 및 요청 가이드 (순수 JavaScript)

`main` 브랜치의 백엔드 DTO를 순수 JavaScript에서 사용하는 방법을 정리한 문서입니다. 아래 JSDoc은 실행 코드가 아니며, VS Code 자동완성과 타입 검사를 돕습니다.

## 공통 설정과 타입

```js
const API_URL = "http://localhost:8080";

/** @typedef {string} UUID */
/** @typedef {string} ISODateTime */

/**
 * @typedef {Object} FieldError
 * @property {string} field
 * @property {string} reason
 */

/**
 * Backend: ApiExceptionHandler.ErrorResponse
 * @typedef {Object} ErrorResponse
 * @property {string} code
 * @property {string} message
 * @property {FieldError[]} fieldErrors
 */

/**
 * Backend: MenuController.PageResponse, AdminOrderController.PageResponse
 * @template T
 * @typedef {Object} PageResponse
 * @property {T[]} content
 * @property {number} page
 * @property {number} size
 * @property {number} totalElements
 * @property {number} totalPages
 * @property {boolean} first
 * @property {boolean} last
 */
```

- 배포 환경에서는 `API_URL`만 실제 서버 주소로 바꿉니다.
- 관리자 API에는 `credentials: "include"`를 사용합니다.
- JSON 요청에는 `Content-Type: application/json`을 지정합니다.
- `204 No Content`에서는 `response.json()`을 호출하지 않습니다.
- 주문 생성의 `Idempotency-Key`는 주문 시도마다 만들고, 같은 주문 재시도에는 같은 값을 사용합니다.
- 실패 응답은 인증 오류를 포함해 `ErrorResponse` 구조로 처리합니다.

## DTO 이름과 반환 구조

### 인증

```js
/**
 * Backend: AuthController.LoginRequest
 * @typedef {Object} LoginRequest
 * @property {string} email
 * @property {string} password
 * @property {boolean} rememberMe
 */

/**
 * Backend: AuthController.LoginResponse
 * @typedef {Object} LoginResponse
 * @property {string} adminName
 */
```

### 가게와 주문 세션

```js
/** @typedef {"OPEN"|"CLOSED"} OperatingStatus */
/** @typedef {"ACTIVE"|"ORDERED"|"EXPIRED"} OrderSessionStatus */
/** @typedef {"DINE_IN"|"TAKEOUT"} FulfillmentType */

/**
 * Backend: StoreController.StoreCreateRequest
 * @typedef {Object} StoreCreateRequest
 * @property {string} name
 */

/**
 * Backend: StoreController.StoreStatusRequest
 * @typedef {Object} StoreStatusRequest
 * @property {OperatingStatus} status
 */

/**
 * Backend: StoreController.StoreStatusResponse
 * @typedef {Object} StoreStatusResponse
 * @property {OperatingStatus} status
 */

/**
 * Backend: StoreController.StoreResponse
 * @typedef {Object} StoreResponse
 * @property {UUID} id
 * @property {string} name
 * @property {OperatingStatus} operatingStatus
 */

/**
 * Backend: PublicStoreController.OrderContextResponse
 * @typedef {Object} OrderContextResponse
 * @property {UUID} storeId
 * @property {string} storeName
 * @property {OperatingStatus} operatingStatus
 * @property {boolean} orderAvailable
 * @property {string} message
 */

/**
 * Backend: OrderSessionController.OrderSessionResponse
 * @typedef {Object} OrderSessionResponse
 * @property {UUID} sessionId
 * @property {UUID} storeId
 * @property {OrderSessionStatus} status
 * @property {number} cartVersion
 * @property {FulfillmentType|null} fulfillmentType
 * @property {ISODateTime} expiresAt
 */

/**
 * Backend: AiAccessTokenController.AiAccessTokenResponse
 * @typedef {Object} AiAccessTokenResponse
 * @property {string} accessToken
 * @property {ISODateTime} expiresAt
 */

/**
 * Backend: FulfillmentController.FulfillmentRequest
 * @typedef {Object} FulfillmentRequest
 * @property {FulfillmentType} fulfillmentType
 */

/**
 * Backend: FulfillmentController.FulfillmentResponse
 * @typedef {Object} FulfillmentResponse
 * @property {UUID} sessionId
 * @property {FulfillmentType} fulfillmentType
 * @property {number} cartVersion
 */
```

### 메뉴

```js
/** @typedef {"COFFEE"|"BEVERAGE"|"TEA"} MenuCategory */
/** @typedef {"AVAILABLE"|"SOLD_OUT"} SalesStatus */
/** @typedef {"HOT"|"ICE"} Temperature */
/** @typedef {"LOW"|"MEDIUM"|"HIGH"} DefaultSweetness */
/** @typedef {"VERY_LOW"|"LOW"|"MEDIUM"|"HIGH"|"VERY_HIGH"} FinalSweetness */
/** @typedef {"REGULAR"|"LARGE"} DrinkSize */
/** @typedef {"NONE"|"SHOT_1"|"SHOT_2"} ExtraShot */
/** @typedef {"LESS"|"NORMAL"|"MORE"} SweetnessAdjustment */
/** @typedef {"TEMPERATURE"|"SIZE"|"EXTRA_SHOT"|"SWEETNESS"} OptionType */
/** @typedef {Temperature|DrinkSize|ExtraShot|SweetnessAdjustment} OptionCode */

/**
 * Backend: MenuController.MenuRequest
 * @typedef {Object} MenuRequest
 * @property {MenuCategory} category
 * @property {string} name
 * @property {string|null} [description]
 * @property {number} price
 * @property {string|null} [imageKey]
 * @property {Temperature[]} availableTemperatures - 한 개 이상 필수
 * @property {DefaultSweetness} defaultSweetness
 * @property {boolean} caffeinated
 * @property {boolean} extraShotAvailable
 */

/**
 * Backend: MenuController.SalesStatusRequest
 * @typedef {Object} SalesStatusRequest
 * @property {SalesStatus} salesStatus
 */

/**
 * Backend: MenuController.OptionResponse
 * @typedef {Object} MenuOptionResponse
 * @property {OptionType} type
 * @property {OptionCode} code
 * @property {string} name
 * @property {number} additionalPrice
 * @property {FinalSweetness|null} finalSweetness - SWEETNESS가 아니면 null
 */

/**
 * Backend: MenuController.MenuResponse
 * @typedef {Object} MenuResponse
 * @property {UUID} id
 * @property {MenuCategory} category
 * @property {string} name
 * @property {string|null} description
 * @property {number} price
 * @property {string|null} imageKey
 * @property {string|null} imageUrl
 * @property {SalesStatus} salesStatus
 * @property {Temperature[]} availableTemperatures
 * @property {DefaultSweetness} defaultSweetness
 * @property {boolean} caffeinated
 * @property {boolean} extraShotAvailable
 * @property {MenuOptionResponse[]} availableOptions
 */

/**
 * Backend: MenuController.ImageUploadResponse
 * @typedef {Object} ImageUploadResponse
 * @property {string} imageKey
 * @property {string} imageUrl
 */

/**
 * Backend: PublicMenuController.OptionValueResponse
 * @typedef {Object} OptionValueResponse
 * @property {UUID} id
 * @property {string} code
 * @property {string} name
 * @property {number} additionalPrice
 * @property {boolean} defaultValue
 */

/**
 * Backend: PublicMenuController.OptionGroupResponse
 * @typedef {Object} OptionGroupResponse
 * @property {UUID} id
 * @property {string} code
 * @property {string} name
 * @property {boolean} required
 * @property {number} minSelections
 * @property {number} maxSelections
 * @property {boolean} requiresSelection
 * @property {UUID|null} autoSelectedOptionId
 * @property {OptionValueResponse[]} values
 */

/**
 * Backend: PublicMenuController.PublicMenuResponse
 * @typedef {MenuResponse & {options: OptionGroupResponse[]}} PublicMenuResponse
 */
```

`availableOptions`는 온도·사이즈·샷·당도 고정 옵션이고, `options`는 메뉴별 옵션 그룹입니다. `extraShotAvailable=false`이면 `availableOptions`에 `EXTRA_SHOT` 항목이 포함되지 않습니다. 메뉴별 그룹에서 `requiresSelection=true`인 항목만 사용자가 선택하며, `autoSelectedOptionId`가 있으면 해당 값을 기본 선택합니다.
관리자 메뉴 생성 시 `options`가 자동 생성됩니다. 장바구니 요청에는 `availableOptions[].code`가 아니라
`options[].values[].id`를 `optionValueIds`로 전달합니다.

### AI 후보를 장바구니 항목으로 변환

AI의 `menu.candidates[].menuId`, `name`, `description`은 후보 표시용 데이터입니다. 최종
확인 모달을 만들기 전에 같은 매장의 현재 메뉴·가격·판매 상태·실제 옵션 UUID를 단건
공개 API로 다시 조회합니다.

```http
GET /api/v1/stores/{storeId}/menus/{candidate.menuId}
```

다른 매장의 `menuId`는 `404 MENU_NOT_FOUND`입니다. FE는 응답의
`salesStatus === "AVAILABLE"`을 확인하고, `requiresSelection=true`인 그룹은 사용자가
`minSelections..maxSelections` 범위로 `values[].id`를 선택하게 합니다.
`autoSelectedOptionId`가 있으면 해당 UUID를 기본값으로 사용합니다. 수량은 1~20만
허용하며, 현재 cart의 `cartVersion`을 `If-Match`로 보내 기존 장바구니 API를 호출합니다.

```http
POST /api/v1/order-sessions/{orderSessionId}/cart/items
If-Match: 0
Content-Type: application/json

{
  "menuId": "<candidate.menuId>",
  "quantity": 1,
  "optionValueIds": ["<PublicMenuResponse.options[].values[].id>"]
}
```

성공 응답의 새 cart를 받은 뒤에만 AI WebSocket으로 `cart.context`를 보내 대화 상태를
동기화합니다. AI 후보의 이름·가격이나 옵션 코드를 장바구니 권한 데이터로 사용하지 않습니다.

### 주문

```js
/** @typedef {"RECEIVED"|"PREPARING"|"COMPLETED"} OrderStatus */
/** @typedef {"PAY_AT_COUNTER"} PaymentMethod */

/**
 * Backend: OrderPreviewService.PreviewOption
 * @typedef {Object} PreviewOption
 * @property {UUID} optionValueId
 * @property {UUID} optionGroupId
 * @property {string} optionGroupCode
 * @property {string} optionGroupName
 * @property {string} code
 * @property {string} name
 * @property {number} additionalPrice
 */

/**
 * Backend: OrderPreviewService.PreviewItem
 * @typedef {Object} PreviewItem
 * @property {UUID} cartItemId
 * @property {UUID} menuId
 * @property {string} menuName
 * @property {number} quantity
 * @property {number} basePrice
 * @property {PreviewOption[]} options
 * @property {number} unitPrice
 * @property {number} totalPrice
 */

/**
 * Backend: OrderPreviewService.OrderPreview
 * @typedef {Object} OrderPreview
 * @property {UUID} sessionId
 * @property {UUID} storeId
 * @property {number} cartVersion
 * @property {FulfillmentType} fulfillmentType
 * @property {PreviewItem[]} items
 * @property {number} totalQuantity
 * @property {number} totalPrice
 * @property {ISODateTime} validatedAt
 */

/**
 * Backend: OrderDtos.OrderOptionsRequest
 * @typedef {Object} OrderOptionsRequest
 * @property {Temperature} temperature
 * @property {DrinkSize} [size=REGULAR]
 * @property {ExtraShot} [extraShot=NONE]
 * @property {SweetnessAdjustment} [sweetness=NORMAL]
 */

/**
 * Backend: OrderDtos.OrderItemRequest
 * @typedef {Object} OrderItemRequest
 * @property {UUID} menuId
 * @property {number} quantity - 1~20
 * @property {OrderOptionsRequest} options
 */

/**
 * Backend: OrderDtos.OrderCreateRequest
 * @typedef {Object} OrderCreateRequest
 * @property {OrderItemRequest[]} items - 1~20개
 */

/**
 * Backend: OrderDtos.OrderOptionResponse
 * @typedef {Object} OrderOptionResponse
 * @property {OptionType} type
 * @property {OptionCode} code
 * @property {string} name
 * @property {number} additionalPrice
 */

/**
 * Backend: OrderDtos.OrderItemResponse
 * @typedef {Object} OrderItemResponse
 * @property {string} menuName
 * @property {number} quantity
 * @property {number} basePrice
 * @property {number} unitPrice
 * @property {number} subtotal
 * @property {OrderOptionResponse[]} options
 * @property {FinalSweetness|null} finalSweetness
 */

/**
 * Backend: OrderDtos.OrderResponse
 * @typedef {Object} OrderResponse
 * @property {UUID} id
 * @property {number} orderNumber
 * @property {OrderStatus} status
 * @property {FulfillmentType|null} fulfillmentType
 * @property {PaymentMethod} paymentMethod
 * @property {OrderItemResponse[]} items
 * @property {number} totalPrice
 * @property {ISODateTime} createdAt
 * @property {ISODateTime} updatedAt
 */

/**
 * Backend: OrderDtos.OrderStatusRequest
 * @typedef {Object} OrderStatusRequest
 * @property {OrderStatus} status
 */

/**
 * Backend: OrderDtos.OrderStatusResponse
 * @typedef {Object} OrderStatusResponse
 * @property {UUID} id
 * @property {number} orderNumber
 * @property {OrderStatus} status
 * @property {FulfillmentType|null} fulfillmentType
 * @property {boolean} pickupReady
 * @property {string} message
 * @property {ISODateTime} updatedAt
 */
```

## API별 DTO 매핑

| 메서드·경로 | 요청 DTO | 응답 DTO | 접근 |
| --- | --- | --- | --- |
| `POST /api/v1/admin/auth/login` | `LoginRequest` | `LoginResponse` | 공개 |
| `POST /api/v1/admin/auth/logout` | 없음 | `204 No Content` | 관리자 |
| `GET /api/v1/admin/stores` | 없음 | `StoreResponse[]` | 관리자 |
| `POST /api/v1/admin/stores` | `StoreCreateRequest` | `StoreResponse` | 관리자 |
| `GET /api/v1/admin/stores/{storeId}/status` | 없음 | `StoreStatusResponse` | 관리자 |
| `PATCH /api/v1/admin/stores/{storeId}/status` | `StoreStatusRequest` | `StoreStatusResponse` | 관리자 |
| `GET /api/v1/stores/{storeId}/order-context` | 없음 | `OrderContextResponse` | 공개 |
| `GET /api/v1/stores/{storeId}/status` | 없음 | `StoreStatusResponse` | 공개 |
| `POST /api/v1/stores/{storeId}/order-sessions` | 없음 | `OrderSessionResponse` | 공개 |
| `POST /api/v1/order-sessions/{sessionId}/ai-token` | 없음 | `AiAccessTokenResponse` | 공개 |
| `PATCH /api/v1/order-sessions/{sessionId}/fulfillment` | `FulfillmentRequest`, Header `If-Match` | `FulfillmentResponse` | 공개 |
| `POST /api/v1/order-sessions/{sessionId}/preview` | Header `If-Match` | `OrderPreview` | 공개 |
| `POST /api/v1/order-sessions/{sessionId}/orders` | Header `If-Match`, `Idempotency-Key` | `OrderResponse` | 공개 |
| `GET /api/v1/admin/stores/{storeId}/menus` | Query `category`, `page`, `size` | `PageResponse<MenuResponse>` | 관리자 |
| `GET /api/v1/admin/stores/{storeId}/menus/{menuId}` | 없음 | `MenuResponse` | 관리자 |
| `POST /api/v1/admin/stores/{storeId}/menus` | `MenuRequest` | `MenuResponse` | 관리자 |
| `PATCH /api/v1/admin/stores/{storeId}/menus/{menuId}` | `MenuRequest` | `MenuResponse` | 관리자 |
| `DELETE /api/v1/admin/stores/{storeId}/menus/{menuId}` | 없음 | `204 No Content` | 관리자 |
| `PATCH /api/v1/admin/stores/{storeId}/menus/{menuId}/sales-status` | `SalesStatusRequest` | `MenuResponse` | 관리자 |
| `POST /api/v1/admin/stores/{storeId}/menus/images` | `FormData(file)` | `ImageUploadResponse` | 관리자 |
| `GET /api/v1/stores/{storeId}/menus` | Query `category`, `page`, `size` | `PageResponse<PublicMenuResponse>` | 공개 |
| `GET /api/v1/stores/{storeId}/menus/{menuId}` | Path `storeId`, `menuId` | `PublicMenuResponse` | 공개 |
| `POST /api/v1/stores/{storeId}/orders` | `OrderCreateRequest` | `OrderResponse` | 공개 |
| `GET /api/v1/orders/{orderId}` | 없음 | `OrderResponse` | 공개 |
| `GET /api/v1/admin/stores/{storeId}/orders` | Query `page`, `size`, 반복 가능한 `status` | `PageResponse<OrderResponse>` | 관리자 |
| `PATCH /api/v1/admin/stores/{storeId}/orders/{orderId}/status` | `OrderStatusRequest` | `OrderResponse` | 관리자 |

메뉴 수정 API는 `PATCH`지만 `MenuRequest`의 필수 필드를 모두 보내야 합니다.

## 생성 요청 예시

### 로그인과 자동 로그인 유지

```js
/** @type {LoginRequest} */
const loginBody = { email, password, rememberMe };

const loginResponse = await fetch(`${API_URL}/api/v1/admin/auth/login`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(loginBody),
});

/** @type {LoginResponse} */
const login = await loginResponse.json();
```

브라우저가 `JSESSIONID` 쿠키를 관리하므로 FE가 쿠키를 직접 저장하거나 읽지 않습니다. 로그인과 이후 모든 관리자 요청에 `credentials: "include"`를 넣으면 `rememberMe` 설정에 따라 서버가 세션 유지 기간을 결정합니다.

### 가게 생성

```js
/** @type {StoreCreateRequest} */
const storeBody = { name: "강남점" };

const storeResponse = await fetch(`${API_URL}/api/v1/admin/stores`, {
  method: "POST",
  credentials: "include",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(storeBody),
});

/** @type {StoreResponse} */
const store = await storeResponse.json();
```

### 주문 세션 생성

```js
const sessionResponse = await fetch(
  `${API_URL}/api/v1/stores/${storeId}/order-sessions`,
  { method: "POST" },
);

/** @type {OrderSessionResponse} */
const session = await sessionResponse.json();
```

### AI WebSocket 액세스 토큰 발급

```js
const tokenResponse = await fetch(
  `${API_URL}/api/v1/order-sessions/${session.sessionId}/ai-token`,
  { method: "POST" },
);

if (!tokenResponse.ok) {
  /** @type {ErrorResponse} */
  const error = await tokenResponse.json();
  throw new Error(`${error.code}: ${error.message}`);
}

/** @type {AiAccessTokenResponse} */
const aiToken = await tokenResponse.json();
```

`accessToken`은 AI WebSocket 연결 직후 보내는 `session.start`에만 사용합니다. 브라우저 저장소나 로그에
남기지 말고 메모리에서 유지하며, 만료 또는 재연결 시 이 API를 다시 호출합니다. 요청에는 `storeId`를 보내지 않습니다.

### 매장/포장 선택

```js
/** @type {FulfillmentRequest} */
const fulfillmentBody = { fulfillmentType: "TAKEOUT" };

const fulfillmentResponse = await fetch(
  `${API_URL}/api/v1/order-sessions/${session.sessionId}/fulfillment`,
  {
    method: "PATCH",
    headers: {
      "Content-Type": "application/json",
      "If-Match": String(session.cartVersion),
    },
    body: JSON.stringify(fulfillmentBody),
  },
);

/** @type {FulfillmentResponse} */
const fulfillment = await fulfillmentResponse.json();
```

### 주문 미리보기 및 최종 검증

```js
const previewResponse = await fetch(
  `${API_URL}/api/v1/order-sessions/${session.sessionId}/preview`,
  {
    method: "POST",
    headers: { "If-Match": String(fulfillment.cartVersion) },
  },
);

/** @type {OrderPreview} */
const preview = await previewResponse.json();
```

미리보기 성공 후 화면에 `items`, `fulfillmentType`, `totalPrice`를 보여주고 최종 주문 여부를 확인합니다.
성공 응답은 재고 예약이 아니므로 주문 생성 요청에도 같은 `cartVersion`을 전달해야 합니다.

### 카운터 결제 주문 생성

```js
const idempotencyKey = crypto.randomUUID();

const checkoutResponse = await fetch(
  `${API_URL}/api/v1/order-sessions/${session.sessionId}/orders`,
  {
    method: "POST",
    headers: {
      "If-Match": String(preview.cartVersion),
      "Idempotency-Key": idempotencyKey,
    },
  },
);

/** @type {OrderResponse} */
const checkoutOrder = await checkoutResponse.json();
```

네트워크 오류로 재시도할 때는 같은 `idempotencyKey`를 재사용합니다. 성공 응답의 `paymentMethod`는
`PAY_AT_COUNTER`이며, 사용자 화면에는 “카운터에서 결제해 주세요”라고 안내합니다.

### 메뉴 생성

```js
/** @type {MenuRequest} */
const menuBody = {
  category: "COFFEE",
  name: "아메리카노",
  description: "고소한 원두",
  price: 4500,
  imageKey: null,
  availableTemperatures: ["HOT", "ICE"],
  defaultSweetness: "MEDIUM",
  caffeinated: true,
  extraShotAvailable: false,
};

const menuResponse = await fetch(
  `${API_URL}/api/v1/admin/stores/${storeId}/menus`,
  {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(menuBody),
  },
);

/** @type {MenuResponse} */
const menu = await menuResponse.json();
```

### 이미지 업로드

```js
const formData = new FormData();
formData.append("file", file);

const imageResponse = await fetch(
  `${API_URL}/api/v1/admin/stores/${storeId}/menus/images`,
  {
    method: "POST",
    credentials: "include",
    body: formData,
  },
);

/** @type {ImageUploadResponse} */
const uploaded = await imageResponse.json();
```

`FormData`에는 브라우저가 boundary를 만들도록 `Content-Type`을 직접 지정하지 않습니다.

### 주문 생성

```js
/** @type {OrderCreateRequest} */
const orderBody = {
  items: [
    {
      menuId,
      quantity: 2,
      options: {
        temperature: "ICE",
        size: "LARGE",
        extraShot: "SHOT_1",
        sweetness: "LESS",
      },
    },
  ],
};

const orderResponse = await fetch(
  `${API_URL}/api/v1/stores/${storeId}/orders`,
  {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "Idempotency-Key": crypto.randomUUID(),
    },
    body: JSON.stringify(orderBody),
  },
);

/** @type {OrderResponse} */
const order = await orderResponse.json();
```

`temperature`만 필수입니다. `size`, `extraShot`, `sweetness`를 생략하면 각각 `REGULAR`, `NONE`, `NORMAL`로 계산됩니다. 옵션 이름과 가격은 보내지 않고 코드만 보냅니다.

### 주문 상태 변경

```js
/** @type {OrderStatusRequest} */
const statusBody = { status: "PREPARING" };

const statusResponse = await fetch(
  `${API_URL}/api/v1/admin/stores/${storeId}/orders/${orderId}/status`,
  {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(statusBody),
  },
);

/** @type {OrderResponse} */
const updatedOrder = await statusResponse.json();
```

## 목록과 SSE 사용

SSE의 연결 순서, 누락 이벤트 복구 및 Postman 테스트는 [주문 SSE 연동 및 테스트 가이드](SSE_GUIDE.md)를 참고합니다.

```js
const menuListResponse = await fetch(
  `${API_URL}/api/v1/stores/${storeId}/menus?category=COFFEE&page=0&size=20`,
);

/** @type {PageResponse<PublicMenuResponse>} */
const menus = await menuListResponse.json();

const orderListResponse = await fetch(
  `${API_URL}/api/v1/admin/stores/${storeId}/orders?page=0&size=20`,
  { credentials: "include" },
);

/** @type {PageResponse<OrderResponse>} */
const orders = await orderListResponse.json();

console.log(orders.content);       // 현재 페이지 주문 목록
console.log(orders.totalElements); // 전체 주문 건수
```

| SSE 경로 | 이벤트 | 데이터 DTO | 접근 |
| --- | --- | --- | --- |
| `/api/v1/admin/stores/{storeId}/orders/stream` | `ORDER_CREATED` | `OrderResponse` | 관리자 |
| `/api/v1/orders/{orderId}/stream` | `ORDER_STATUS_CHANGED` | `OrderStatusResponse` | 공개 |
| `/api/v1/orders/{orderId}/stream` | `PICKUP_READY` | `OrderStatusResponse` | 공개 |
| 두 경로 | `HEARTBEAT` | `{}` | 경로에 따름 |

```js
const source = new EventSource(
  `${API_URL}/api/v1/admin/stores/${storeId}/orders/stream`,
  { withCredentials: true },
);

source.addEventListener("ORDER_CREATED", (event) => {
  /** @type {OrderResponse} */
  const newOrder = JSON.parse(event.data);
  console.log(newOrder);
});
```

고객 주문 SSE는 `withCredentials` 없이 연결하며 주문이 `COMPLETED`가 되면 서버에서 종료됩니다.

```js
const orderSource = new EventSource(
  `${API_URL}/api/v1/orders/${orderId}/stream`,
);

orderSource.addEventListener("ORDER_STATUS_CHANGED", (event) => {
  /** @type {OrderStatusResponse} */
  const status = JSON.parse(event.data);
  renderOrderStatus(status);
});

orderSource.addEventListener("PICKUP_READY", (event) => {
  /** @type {OrderStatusResponse} */
  const status = JSON.parse(event.data);

  showPickupOverlay(status.message); // 큰 글씨, 고대비 색상, 화면 깜빡임은 FE에서 처리
  if ("vibrate" in navigator) {
    navigator.vibrate([300, 150, 300]);
  }
  orderSource.close(); // EventSource 자동 재연결 방지
});
```

`navigator.vibrate()`는 지원 기기에서만 동작하므로 화면 강조와 안내 문구를 기본 알림 수단으로 사용합니다.
페이지 진입·새로고침 시에는 먼저 `GET /api/v1/orders/{orderId}`로 현재 상태를 조회한 뒤 SSE를 연결합니다.
이미 완료된 주문의 과거 SSE 이벤트는 재전송하지 않으므로, 조회 결과의 `pickupReady=true`도 동일한 픽업 UI를
표시하고 SSE는 연결하지 않습니다.
