// VITE_API_URL is baked in at build time (Vite only exposes vars present when
// `vite build` runs). Local dev points at the standalone uvicorn server via
// .env.development; production points at the same-origin /api mount via
// .env.production (see vercel.json's services + rewrites). No localhost
// fallback here on purpose — if this is ever unset in a real deploy, API
// calls should fail loudly (relative-path 404s) rather than silently trying
// to reach a developer's own machine.
const API_URL = import.meta.env.VITE_API_URL ?? "";

export class ApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

function getToken(): string | null {
  return localStorage.getItem("pv_token");
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const token = getToken();
  const headers: Record<string, string> = {
    ...(options.headers as Record<string, string> | undefined),
  };
  if (token) headers["Authorization"] = `Bearer ${token}`;
  if (!(options.body instanceof FormData) && options.body) {
    headers["Content-Type"] = "application/json";
  }

  const res = await fetch(`${API_URL}${path}`, { ...options, headers });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const data = await res.json();
      detail = data.detail || detail;
    } catch {
      /* ignore */
    }
    throw new ApiError(res.status, detail);
  }

  const contentType = res.headers.get("content-type") || "";
  if (contentType.includes("application/json")) {
    return res.json();
  }
  return res as unknown as T;
}

export const api = {
  get: <T>(path: string) => request<T>(path, { method: "GET" }),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      body: body instanceof FormData ? body : body !== undefined ? JSON.stringify(body) : undefined,
    }),
  postForm: <T>(path: string, form: FormData) =>
    request<T>(path, { method: "POST", body: form }),
  raw: (path: string, options: RequestInit = {}) => {
    const token = getToken();
    const headers: Record<string, string> = { ...(options.headers as Record<string, string> | undefined) };
    if (token) headers["Authorization"] = `Bearer ${token}`;
    if (options.body && !(options.body instanceof FormData)) {
      headers["Content-Type"] = "application/json";
    }
    return fetch(`${API_URL}${path}`, { ...options, headers });
  },
};

export { getToken };
export const setToken = (token: string) => localStorage.setItem("pv_token", token);
export const clearToken = () => localStorage.removeItem("pv_token");
