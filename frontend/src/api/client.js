export const API_URL = import.meta.env?.VITE_API_URL || "http://localhost:8080";
export const ADMIN_SESSION_KEY = "silki-admin-session";

export const getAdminSession = () => {
  try {
    return JSON.parse(localStorage.getItem(ADMIN_SESSION_KEY));
  } catch {
    return null;
  }
};

export const setAdminSession = (session) =>
  localStorage.setItem(ADMIN_SESSION_KEY, JSON.stringify(session));

export const clearAdminSession = () =>
  localStorage.removeItem(ADMIN_SESSION_KEY);

export const request = async (path, { body, headers, ...options } = {}) => {
  const isFormData = body instanceof FormData;
  const response = await fetch(`${API_URL}${path}`, {
    credentials: "include",
    ...options,
    headers: {
      ...(!isFormData && body !== undefined
        ? { "Content-Type": "application/json" }
        : {}),
      ...headers,
    },
    body: isFormData || body === undefined ? body : JSON.stringify(body),
  });

  if (response.status === 401 && path.startsWith("/api/v1/admin/") && !path.endsWith("/auth/login")) {
    clearAdminSession();
    if (typeof window !== "undefined") window.location.assign("/login");
  }

  if (!response.ok) {
    const data = await response.json().catch(() => ({}));
    throw Object.assign(new Error(data.message || "요청을 처리하지 못했습니다."), {
      status: response.status,
      code: data.code,
      fieldErrors: data.fieldErrors || [],
    });
  }

  return response.status === 204 ? undefined : response.json();
};
