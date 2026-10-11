import { request } from "./client";

export const login = (email, password, rememberMe) =>
  request("/api/v1/admin/auth/login", {
    method: "POST",
    body: { email, password, rememberMe },
  });

export const logout = () =>
  request("/api/v1/admin/auth/logout", { method: "POST" });
