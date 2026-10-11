import { request } from "./client.js";

const basePath = (storeId) => `/api/v1/admin/stores/${storeId}/menus`;
const publicBasePath = (storeId) => `/api/v1/stores/${storeId}/menus`;
const menuCategories = ["COFFEE", "BEVERAGE", "TEA"];

export const getMenus = (storeId, category, page = 0, size = 20) =>
  request(`${basePath(storeId)}?${new URLSearchParams({ category, page, size })}`);

export const getMenu = (storeId, menuId) =>
  request(`${basePath(storeId)}/${menuId}`);

export const getPublicMenus = (storeId, category, page = 0, size = 20) =>
  request(`${publicBasePath(storeId)}?${new URLSearchParams({ category, page, size })}`);

export const hasPublicMenuData = async (storeId) => {
  const categoryPages = await Promise.all(
    menuCategories.map((category) => getPublicMenus(storeId, category, 0, 1)),
  );
  return categoryPages.some(({ content }) => content.length > 0);
};

export const uploadMenuImage = (storeId, file) => {
  const body = new FormData();
  body.append("file", file);
  return request(`${basePath(storeId)}/images`, { method: "POST", body });
};

export const createMenu = (storeId, menu) =>
  request(basePath(storeId), { method: "POST", body: menu });

export const updateMenu = (storeId, menuId, menu) =>
  request(`${basePath(storeId)}/${menuId}`, { method: "PATCH", body: menu });

export const deleteMenu = (storeId, menuId) =>
  request(`${basePath(storeId)}/${menuId}`, { method: "DELETE" });

export const updateMenuSalesStatus = (storeId, menuId, salesStatus) =>
  request(`${basePath(storeId)}/${menuId}/sales-status`, {
    method: "PATCH",
    body: { salesStatus },
  });
