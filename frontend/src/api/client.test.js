import test from "node:test";
import assert from "node:assert/strict";
import { request } from "./client.js";
import {
  checkoutOrder,
  filterOrdersByStatus,
  getCartPath,
  getStoreIdFromQr,
  getVoiceOrderPathFromQr,
  isCartConfirmed,
  mergeOrder,
  replaceCart,
  sortOrders,
  subscribeToOrderStatus,
  updateVisibleOrders,
} from "./orders.js";
import { hasPublicMenuData } from "./menus.js";
import { getOrderContext } from "./stores.js";

test("request handles JSON, errors, and empty responses", async () => {
  const calls = [];
  globalThis.fetch = async (_url, options) => {
    calls.push(options);
    return calls.length === 1
      ? new Response(JSON.stringify({ ok: true }), { status: 200 })
      : calls.length === 2
        ? new Response(JSON.stringify({ uploaded: true }), { status: 200 })
        : calls.length === 3
          ? new Response(null, { status: 204 })
          : new Response(JSON.stringify({ code: "BAD", message: "실패", fieldErrors: [] }), { status: 400 });
  };

  assert.deepEqual(await request("/ok", { method: "POST", body: { value: 1 } }), { ok: true });
  assert.equal(calls[0].credentials, "include");
  assert.equal(calls[0].headers["Content-Type"], "application/json");
  const formData = new FormData();
  formData.append("file", new Blob(["image"]), "menu.png");
  assert.deepEqual(await request("/upload", { method: "POST", body: formData }), { uploaded: true });
  assert.equal(calls[1].headers["Content-Type"], undefined);
  assert.equal(calls[1].body, formData);
  assert.equal(await request("/empty"), undefined);
  await assert.rejects(request("/error"), (error) => error.code === "BAD" && error.status === 400);
});

test("orders are sorted by workflow status", () => {
  const orders = [{ status: "COMPLETED" }, { status: "RECEIVED" }, { status: "PREPARING" }];
  assert.deepEqual(sortOrders(orders).map(({ status }) => status), ["RECEIVED", "PREPARING", "COMPLETED"]);
});

test("order tabs only show their statuses", () => {
  const orders = [{ status: "COMPLETED" }, { status: "RECEIVED" }, { status: "PREPARING" }];
  assert.deepEqual(filterOrdersByStatus(orders, ["RECEIVED", "PREPARING"]), orders.slice(1));
  assert.deepEqual(filterOrdersByStatus(orders, ["COMPLETED"]), orders.slice(0, 1));
});

test("completed orders leave the active list", () => {
  const orders = [{ id: "1", status: "PREPARING" }, { id: "2", status: "RECEIVED" }];
  assert.deepEqual(updateVisibleOrders(orders, { id: "1", status: "COMPLETED" }, true), [orders[1]]);
});

test("status updates preserve customer order details", () => {
  const items = [{ menuName: "아메리카노", options: [] }];
  assert.deepEqual(
    mergeOrder({ id: "1", status: "RECEIVED", items }, { id: "1", status: "PREPARING" }),
    { id: "1", status: "PREPARING", items },
  );
});

test("cart replacement and checkout send concurrency headers", async () => {
  const calls = [];
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options });
    return new Response(JSON.stringify({ id: "order-1" }), { status: 201 });
  };

  await replaceCart("session-1", 3, [{ menuId: "menu-1", quantity: 1, optionValueIds: [] }]);
  await checkoutOrder("session-1", 4, "attempt-1");

  assert.equal(calls[0].url, "http://localhost:8080/api/v1/order-sessions/session-1/cart");
  assert.equal(calls[0].options.method, "PUT");
  assert.equal(calls[0].options.headers["If-Match"], 3);
  assert.equal(calls[1].url, "http://localhost:8080/api/v1/order-sessions/session-1/orders");
  assert.equal(calls[1].options.headers["If-Match"], 4);
  assert.equal(calls[1].options.headers["Idempotency-Key"], "attempt-1");
});

test("only a complete AI confirmation can replace the cart", () => {
  const id = "123e4567-e89b-12d3-a456-426614174000";
  const action = {
    type: "cart.confirmed",
    aiSessionId: id,
    turnId: id,
    basedOnCartVersion: 2,
    fulfillmentType: "TAKEOUT",
    items: [{
      menuId: id,
      quantity: 3,
      optionValueIds: [id],
    }],
  };

  assert.equal(isCartConfirmed(action), true);
  assert.equal(isCartConfirmed({ ...action, type: "menu.candidates" }), false);
  assert.equal(isCartConfirmed({ ...action, basedOnCartVersion: -1 }), false);
  assert.equal(isCartConfirmed({ ...action, items: [{ ...action.items[0], quantity: 0 }] }), false);
});

test("QR accepts a store UUID or a voice-order URL with one", () => {
  const id = "123e4567-e89b-12d3-a456-426614174000";
  assert.equal(getStoreIdFromQr(id, "https://silki.test"), id);
  assert.equal(getVoiceOrderPathFromQr(id, "https://silki.test"), `/voice-order?storeId=${id}`);
  assert.equal(
    getStoreIdFromQr(`https://silki.test/voice-order?storeId=${id}`, "https://silki.test"),
    id,
  );
  assert.equal(
    getVoiceOrderPathFromQr(`https://silki.test/voice-order?storeId=${id}`, "https://silki.test"),
    `/voice-order?storeId=${id}`,
  );
  assert.equal(getVoiceOrderPathFromQr(`https://silki.test/menu?storeId=${id}`, "https://silki.test"), null);
  assert.equal(getVoiceOrderPathFromQr(`https://other.test/voice-order?storeId=${id}`, "https://silki.test"), null);
});

test("voice ordering finishes on the cart route with the same store and session", () => {
  const storeId = "123e4567-e89b-12d3-a456-426614174000";
  const sessionId = "223e4567-e89b-12d3-a456-426614174000";

  assert.equal(
    getCartPath(storeId, sessionId),
    `/cart?storeId=${storeId}&sessionId=${sessionId}`,
  );
  assert.equal(getCartPath(storeId, "missing"), null);
});

test("QR store validation uses public store and menu APIs", async () => {
  const id = "123e4567-e89b-12d3-a456-426614174000";
  const calls = [];
  globalThis.fetch = async (url) => {
    calls.push(url);
    if (url.endsWith("/order-context")) {
      return new Response(JSON.stringify({
        storeId: id,
        storeName: "강남점",
        operatingStatus: "OPEN",
        orderAvailable: true,
        message: "현재 주문 가능합니다.",
      }), { status: 200 });
    }
    const hasMenu = url.includes("category=BEVERAGE");
    return new Response(JSON.stringify({ content: hasMenu ? [{ id: "menu-1" }] : [] }), {
      status: 200,
    });
  };

  assert.equal((await getOrderContext(id)).storeName, "강남점");
  assert.equal(await hasPublicMenuData(id), true);
  assert.equal(calls.length, 4);
  assert.ok(calls.some((url) => url.includes(`/api/v1/stores/${id}/menus?category=COFFEE`)));
  assert.ok(calls.some((url) => url.includes(`/api/v1/stores/${id}/menus?category=BEVERAGE`)));
  assert.ok(calls.some((url) => url.includes(`/api/v1/stores/${id}/menus?category=TEA`)));
});

test("customer SSE parses status events and closes", () => {
  const listeners = {};
  let closed = false;
  globalThis.EventSource = class {
    addEventListener(name, listener) { listeners[name] = listener; }
    close() { closed = true; }
  };
  let received;
  const close = subscribeToOrderStatus("order-1", (status) => { received = status; });

  listeners.ORDER_STATUS_CHANGED({ data: JSON.stringify({ id: "order-1", status: "PREPARING" }) });
  close();

  assert.deepEqual(received, { id: "order-1", status: "PREPARING" });
  assert.equal(closed, true);
});
