const ACCESS = "psych_atlas_access";
const REFRESH = "psych_atlas_refresh";

export function getAccessToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS);
}

export function getRefreshToken() {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(REFRESH);
}

export function setTokens(access: string, refresh?: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS, access);
  if (refresh) localStorage.setItem(REFRESH, refresh);
  window.dispatchEvent(new Event("auth-change"));
}

export function clearTokens() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS);
  localStorage.removeItem(REFRESH);
  window.dispatchEvent(new Event("auth-change"));
}

export function hasToken() {
  return Boolean(getAccessToken() || getRefreshToken());
}
