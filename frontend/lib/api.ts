import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

export class ApiError extends Error {
  status: number;
  code?: string;

  constructor(status: number, message: string, code?: string) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
  }
}

let refreshInFlight: Promise<string | null> | null = null;

async function performRefresh(): Promise<string | null> {
  const refresh = getRefreshToken();
  if (!refresh) return null;

  const response = await fetch(`${API_URL}/auth/refresh/`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ refresh }),
    cache: "no-store"
  });

  if (!response.ok) {
    clearTokens();
    return null;
  }

  const data = await response.json();
  setTokens(data.access, data.refresh || refresh);
  return data.access;
}

function refreshAccessToken(): Promise<string | null> {
  if (!refreshInFlight) {
    refreshInFlight = performRefresh().finally(() => {
      refreshInFlight = null;
    });
  }
  return refreshInFlight;
}

async function parseError(response: Response) {
  let message = `خطای درخواست (${response.status})`;
  let code: string | undefined;
  try {
    const body = await response.json();
    message = body.detail || JSON.stringify(body);
    if (typeof body.code === "string") code = body.code;
  } catch {}
  return { message, code };
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  authenticated = false
): Promise<T> {
  const makeRequest = async (token?: string | null) => {
    const headers = new Headers(options.headers);
    if (options.body != null && !headers.has("Content-Type")) {
      headers.set("Content-Type", "application/json");
    }
    if (authenticated && token) headers.set("Authorization", `Bearer ${token}`);

    return fetch(`${API_URL}${path}`, {
      ...options,
      headers,
      cache: "no-store"
    });
  };

  let token = authenticated ? getAccessToken() : null;
  if (authenticated && !token) token = await refreshAccessToken();
  if (authenticated && !token) throw new Error("برای ادامه باید وارد حساب شوی.");

  let response = await makeRequest(token);
  if (authenticated && response.status === 401) {
    token = await refreshAccessToken();
    if (token) response = await makeRequest(token);
  }

  if (!response.ok) {
    if (response.status === 401) clearTokens();
    const error = await parseError(response);
    throw new ApiError(response.status, error.message, error.code);
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function publicFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) {
    const error = await parseError(response);
    throw new ApiError(response.status, error.message, error.code);
  }
  return response.json();
}
