const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export class ApiRequestError extends Error {
  constructor(message, { status = 0, code = "REQUEST_FAILED" } = {}) {
    super(message);
    this.name = "ApiRequestError";
    this.status = status;
    this.code = code;
  }
}

const readResponseBody = async (response) => {
  const text = await response.text();

  if (!text) {
    return null;
  }

  try {
    return JSON.parse(text);
  } catch {
    return { message: text };
  }
};

const requestJson = async (path, options) => {
  let response;

  try {
    response = await fetch(`${API_BASE_URL}${path}`, {
      ...options,
      cache: "no-store",
      headers: {
        Accept: "application/json",
        ...options?.headers,
      },
    });
  } catch (error) {
    if (error?.name === "AbortError") {
      throw error;
    }

    throw new ApiRequestError("서버에 연결할 수 없습니다. 네트워크를 확인해주세요.", {
      code: "NETWORK_ERROR",
    });
  }

  const body = await readResponseBody(response);

  if (!response.ok) {
    throw new ApiRequestError(
      body?.message || "요청을 처리하지 못했습니다. 잠시 후 다시 시도해주세요.",
      {
        status: response.status,
        code: body?.code || `HTTP_${response.status}`,
      },
    );
  }

  return body;
};

export const createOrderSession = (storeId, { signal } = {}) =>
  requestJson(`/api/v1/stores/${encodeURIComponent(storeId)}/order-sessions`, {
    method: "POST",
    signal,
  });

export const issueAiAccessToken = (orderSessionId, { signal } = {}) =>
  requestJson(
    `/api/v1/order-sessions/${encodeURIComponent(orderSessionId)}/ai-token`,
    {
      method: "POST",
      signal,
    },
  );

export const getCart = (orderSessionId, { signal } = {}) =>
  requestJson(`/api/v1/order-sessions/${encodeURIComponent(orderSessionId)}/cart`, {
    method: "GET",
    signal,
  });

export const addCartItem = (
  orderSessionId,
  { cartVersion, menuId, quantity = 1, optionValueIds = [] },
  { signal } = {},
) =>
  requestJson(
    `/api/v1/order-sessions/${encodeURIComponent(orderSessionId)}/cart/items`,
    {
      method: "POST",
      signal,
      headers: {
        "Content-Type": "application/json",
        "If-Match": String(cartVersion),
      },
      body: JSON.stringify({ menuId, quantity, optionValueIds }),
    },
  );

export const getPublicMenu = (storeId, menuId, { signal } = {}) =>
  requestJson(
    `/api/v1/stores/${encodeURIComponent(storeId)}/menus/${encodeURIComponent(menuId)}`,
    {
      method: "GET",
      signal,
    },
  );

export const toAiCartItems = (cart) =>
  Array.isArray(cart?.items)
    ? cart.items.map((item) => ({
        menuId: String(item.menuId),
        quantity: item.quantity,
        optionIds: Array.isArray(item.options)
          ? item.options.map((option) => String(option.optionValueId))
          : [],
      }))
    : [];

export const getAiWebSocketUrl = () => {
  const configuredUrl = (import.meta.env.VITE_AI_WS_URL || "").trim();

  if (configuredUrl) {
    const url = new URL(configuredUrl, window.location.href);

    if (url.protocol === "http:") {
      url.protocol = "ws:";
    } else if (url.protocol === "https:") {
      url.protocol = "wss:";
    }

    if (url.protocol !== "ws:" && url.protocol !== "wss:") {
      throw new ApiRequestError("VITE_AI_WS_URL은 ws:// 또는 wss:// 주소여야 합니다.", {
        code: "INVALID_WS_URL",
      });
    }

    if (window.location.protocol === "https:" && url.protocol !== "wss:") {
      throw new ApiRequestError("HTTPS 화면에서는 AI WebSocket도 wss://를 사용해야 합니다.", {
        code: "INSECURE_WS_URL",
      });
    }

    return url.toString();
  }

  const protocol = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${protocol}//${window.location.host}/ai/ws`;
};
