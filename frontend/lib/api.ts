import { clearTokens, getAccessToken, getRefreshToken, setTokens } from "./auth";

export const API_URL =
  process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000/api";

async function refreshAccessToken(): Promise<string | null> {
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

async function parseError(response: Response) {
  let detail = `خطای درخواست (${response.status})`;
  try {
    const body = await response.json();
    detail = body.detail || JSON.stringify(body);
  } catch {}
  return detail;
}

export async function api<T>(
  path: string,
  options: RequestInit = {},
  authenticated = false
): Promise<T> {
  const makeRequest = async (token?: string | null) => {
    const headers = new Headers(options.headers);
    headers.set("Content-Type", "application/json");
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
    throw new Error(await parseError(response));
  }

  if (response.status === 204) return undefined as T;
  return response.json();
}

export async function publicFetch<T>(path: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  if (!response.ok) throw new Error(await parseError(response));
  return response.json();
}
