# 주문 SSE 연동 및 테스트 가이드

주문 관련 SSE는 서버에서 변경이 발생한 즉시 전달됩니다. 20초 주기의 `HEARTBEAT`는 이벤트 지연 시간이 아니라 연결 유지 및 상태 확인용입니다.

## 이벤트 명세

| 대상 | 연결 경로 | 이벤트 | 데이터 DTO | 인증 |
| --- | --- | --- | --- | --- |
| 관리자 | `GET /api/v1/admin/stores/{storeId}/orders/stream` | `ORDER_CREATED` | `OrderResponse` | 관리자 세션 쿠키 필요 |
| 고객 | `GET /api/v1/orders/{orderId}/stream` | `ORDER_STATUS_CHANGED` | `OrderStatusResponse` | 공개 |
| 공통 | 위 연결 | `HEARTBEAT` | `{}` | 연결 경로에 따름 |

- `ORDER_CREATED`: 고객 주문의 DB 트랜잭션이 커밋된 직후 발행됩니다.
- `ORDER_STATUS_CHANGED`: 관리자의 상태 변경 트랜잭션이 커밋된 직후 발행됩니다.
- 주문 상태는 `RECEIVED → PREPARING → COMPLETED` 순서로만 변경할 수 있습니다.
- 고객 SSE는 `COMPLETED` 이벤트를 보낸 뒤 서버에서 종료합니다.
- 한 연결의 서버 타임아웃은 30분이며 브라우저 `EventSource`는 연결 종료 시 자동 재연결을 시도합니다.

## 관리자: 신규 주문 수신

관리자 SSE를 먼저 연결한 다음 현재 주문 목록을 조회합니다. 이 순서로 연결 중 발생한 주문도 목록 조회 결과와 합칠 수 있습니다. `order.id`를 기준으로 중복을 제거합니다.

```js
const ordersById = new Map();

const source = new EventSource(
  `${API_URL}/api/v1/admin/stores/${storeId}/orders/stream`,
  { withCredentials: true },
);

source.addEventListener("ORDER_CREATED", (event) => {
  const order = JSON.parse(event.data);
  ordersById.set(order.id, order);
  renderOrders([...ordersById.values()]);
});

source.addEventListener("HEARTBEAT", () => {
  console.debug("admin SSE connected");
});

const response = await fetch(
  `${API_URL}/api/v1/admin/stores/${storeId}/orders?page=0&size=20`,
  { credentials: "include" },
);
const page = await response.json();
page.content.forEach((order) => ordersById.set(order.id, order));
renderOrders([...ordersById.values()]);
```

관리자 로그인과 SSE 요청의 호스트가 같아야 Postman Cookie Jar 또는 브라우저가 같은 `JSESSIONID`를 전송합니다. 브라우저에서는 `withCredentials: true`가 필요합니다.

## 고객: 주문 상태 수신

주문 생성 응답의 `id`를 `orderId`로 사용합니다. SSE 리스너를 등록한 뒤 REST 상태 조회로 현재 값을 맞춥니다.

```js
const source = new EventSource(
  `${API_URL}/api/v1/orders/${orderId}/stream`,
);

source.addEventListener("ORDER_STATUS_CHANGED", (event) => {
  const orderStatus = JSON.parse(event.data);
  renderOrderStatus(orderStatus.status);

  if (orderStatus.status === "COMPLETED") {
    source.close();
  }
});

source.addEventListener("HEARTBEAT", () => {
  console.debug("customer SSE connected");
});

const response = await fetch(`${API_URL}/api/v1/orders/${orderId}`);
const current = await response.json();
renderOrderStatus(current.status);
```

`ORDER_STATUS_CHANGED` 데이터는 다음 구조입니다.

```json
{
  "id": "주문 UUID",
  "orderNumber": 12,
  "status": "PREPARING"
}
```

## 연결 복구

현재 서버는 SSE 이벤트를 저장하거나 재전송하지 않습니다. 연결이 끊긴 동안 발생한 변경은 다음 REST API로 다시 맞춰야 합니다.

- 관리자: `GET /api/v1/admin/stores/{storeId}/orders?page=0&size=20`
- 고객: `GET /api/v1/orders/{orderId}`

`EventSource.onerror`가 발생하면 화면에 오류를 확정 표시하기보다 REST API를 다시 조회합니다. 브라우저의 자동 재연결은 유지합니다.

```js
source.onerror = async () => {
  const response = await fetch(`${API_URL}/api/v1/orders/${orderId}`);
  if (response.ok) {
    const current = await response.json();
    renderOrderStatus(current.status);
  }
};
```

## Postman으로 신규 주문 테스트

1. `POST /api/v1/admin/auth/login`으로 로그인하고 Cookie Jar의 `JSESSIONID`를 확인합니다.
2. `GET /api/v1/admin/stores/{storeId}/orders/stream`을 실행하고 연결을 유지합니다.
3. 최대 20초 안에 `HEARTBEAT`가 표시되는지 확인합니다.
4. 다른 탭에서 `POST /api/v1/stores/{storeId}/orders`로 주문을 생성합니다.
5. SSE 탭에서 `ORDER_CREATED`와 주문 JSON을 확인합니다.

주문 요청마다 새 멱등키를 사용합니다.

```http
Idempotency-Key: {{$guid}}
```

기존 `Idempotency-Key`를 재사용하면 저장된 주문만 반환하고 `ORDER_CREATED`를 다시 발행하지 않습니다. SSE 경로와 주문 생성 경로의 `storeId`도 같아야 합니다.

## Postman으로 고객 상태 변경 테스트

1. 주문 생성 응답에서 `id`를 복사합니다.
2. `GET /api/v1/orders/{orderId}/stream`을 실행하고 연결을 유지합니다.
3. 다른 탭에서 관리자 API로 `RECEIVED` 주문을 `PREPARING`으로 변경합니다.

```http
PATCH /api/v1/admin/stores/{storeId}/orders/{orderId}/status
Content-Type: application/json
```

```json
{
  "status": "PREPARING"
}
```

4. 고객 SSE 탭에서 `ORDER_STATUS_CHANGED`를 확인합니다.
5. 같은 방식으로 `COMPLETED`로 변경하고 마지막 이벤트 이후 연결이 종료되는지 확인합니다.

## 현재 구조의 범위

SSE 구독 정보는 애플리케이션 메모리에 저장됩니다. 따라서 현재 구조는 백엔드 인스턴스가 하나일 때를 기준으로 합니다. 여러 인스턴스로 운영할 때는 Redis Pub/Sub 같은 공용 메시지 전달 계층과 이벤트 재처리 전략이 필요합니다.
