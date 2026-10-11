import { request } from "./client.js";

export const getStores = () => request("/api/v1/admin/stores");

export const getOrderContext = (storeId) =>
  request(`/api/v1/stores/${storeId}/order-context`);

export const getStoreStatus = (storeId) =>
  request(`/api/v1/admin/stores/${storeId}/status`);

export const updateStoreStatus = (storeId, status) =>
  request(`/api/v1/admin/stores/${storeId}/status`, {
    method: "PATCH",
    body: { status },
  });
