import { API_URL, request } from "./client.js";

const basePath = (storeId) => `/api/v1/admin/stores/${storeId}/orders`;
const statusPriority = { RECEIVED: 0, PREPARING: 1, COMPLETED: 2 };
const uuidPattern = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const fulfillmentTypes = new Set(["DINE_IN", "TAKEOUT"]);
export const CART_CONFIRMED_EVENT = "silki:cart-confirmed";

export const isUuid = (value) => uuidPattern.test(value || "");

export const getStoreIdFromQr = (value, origin = window.location.origin) => {
  if (isUuid(value?.trim())) return value.trim();

  try {
    const url = new URL(value, origin);
    const storeId = url.searchParams.get("storeId");
    return url.origin === origin && url.pathname === "/voice-order" && isUuid(storeId)
      ? storeId
      : null;
  } catch {
    return null;
  }
};

export const isCartConfirmed = (message) =>
  message?.type === "cart.confirmed" && isUuid(message.aiSessionId) && isUuid(message.turnId) &&
  Number.isInteger(message.basedOnCartVersion) && message.basedOnCartVersion >= 0 &&
  (message.fulfillmentType == null || fulfillmentTypes.has(message.fulfillmentType)) &&
  Array.isArray(message.items) && message.items.length > 0 && message.items.length <= 20 &&
  message.items.every(({ menuId, quantity, optionValueIds }) =>
    isUuid(menuId) && Number.isInteger(quantity) && quantity >= 1 && quantity <= 20 &&
    Array.isArray(optionValueIds) && optionValueIds.length <= 20 &&
    optionValueIds.every(isUuid) && new Set(optionValueIds).size === optionValueIds.length,
  );

export const getVoiceOrderPathFromQr = (value, origin = window.location.origin) => {
  const storeId = getStoreIdFromQr(value, origin);
  return storeId ? `/voice-order?${new URLSearchParams({ storeId })}` : null;
};

export const getCartPath = (storeId, sessionId) =>
  isUuid(storeId) && isUuid(sessionId)
    ? `/cart?${new URLSearchParams({ storeId, sessionId })}`
    : null;

export const sortOrders = (orders) =>
  [...orders].sort((left, right) => statusPriority[left.status] - statusPriority[right.status]);

export const filterOrdersByStatus = (orders, statuses) =>
  orders.filter(({ status }) => statuses.includes(status));

export const updateVisibleOrders = (orders, updated, hideCompleted) =>
  hideCompleted && updated.status === "COMPLETED"
    ? orders.filter(({ id }) => id !== updated.id)
    : orders.map((order) => order.id === updated.id ? updated : order);

export const mergeOrder = (current, updated) => ({
  ...current,
  ...updated,
  items: updated.items ?? current?.items ?? [],
});

export const getOrders = (storeId, { page = 0, size = 20, statuses = [] } = {}) => {
  const query = new URLSearchParams({ page, size });
  statuses.forEach((status) => query.append("status", status));
  return request(`${basePath(storeId)}?${query}`);
};

export const updateOrderStatus = (storeId, orderId, status) =>
  request(`${basePath(storeId)}/${orderId}/status`, {
    method: "PATCH",
    body: { status },
  });

export const createOrderSession = (storeId) =>
  request(`/api/v1/stores/${storeId}/order-sessions`, { method: "POST" });

export const getCart = (sessionId) => request(`/api/v1/order-sessions/${sessionId}/cart`);

export const replaceCart = (sessionId, cartVersion, items) =>
  request(`/api/v1/order-sessions/${sessionId}/cart`, {
    method: "PUT",
    headers: { "If-Match": cartVersion },
    body: { items },
  });

export const updateCartItem = (sessionId, cartItemId, cartVersion, quantity, optionValueIds) =>
  request(`/api/v1/order-sessions/${sessionId}/cart/items/${cartItemId}`, {
    method: "PATCH",
    headers: { "If-Match": cartVersion },
    body: { quantity, optionValueIds },
  });

export const deleteCartItem = (sessionId, cartItemId, cartVersion) =>
  request(`/api/v1/order-sessions/${sessionId}/cart/items/${cartItemId}`, {
    method: "DELETE",
    headers: { "If-Match": cartVersion },
  });

export const selectFulfillment = (sessionId, cartVersion, fulfillmentType) =>
  request(`/api/v1/order-sessions/${sessionId}/fulfillment`, {
    method: "PATCH",
    headers: { "If-Match": cartVersion },
    body: { fulfillmentType },
  });

export const checkoutOrder = (sessionId, cartVersion, idempotencyKey) =>
  request(`/api/v1/order-sessions/${sessionId}/orders`, {
    method: "POST",
    headers: { "If-Match": cartVersion, "Idempotency-Key": idempotencyKey },
  });

export const getOrder = (orderId) => request(`/api/v1/orders/${orderId}`);

export const subscribeToOrderStatus = (orderId, onStatus, onError) => {
  const source = new EventSource(`${API_URL}/api/v1/orders/${orderId}/stream`);
  source.addEventListener("ORDER_STATUS_CHANGED", (event) =>
    onStatus(JSON.parse(event.data)),
  );
  if (onError) source.onerror = onError;
  return () => source.close();
};

export const subscribeToOrders = (storeId, onOrder, onError) => {
  const source = new EventSource(`${API_URL}${basePath(storeId)}/stream`, {
    withCredentials: true,
  });
  source.addEventListener("ORDER_CREATED", (event) =>
    onOrder(JSON.parse(event.data)),
  );
  if (onError) source.onerror = onError;
  return () => source.close();
};
