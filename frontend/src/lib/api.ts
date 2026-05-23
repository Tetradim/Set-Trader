// Support both VITE_ (Vite) and REACT_APP_ (Create React App) prefixes
const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.REACT_APP_BACKEND_URL || '';
const AUTH_TOKEN_KEY = 'sentinel_auth_token';

export function getAuthToken(): string | null {
  return localStorage.getItem(AUTH_TOKEN_KEY);
}

export function setAuthToken(token: string): void {
  localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken(): void {
  localStorage.removeItem(AUTH_TOKEN_KEY);
}

export async function apiFetch(path: string, options?: RequestInit & { rawText?: boolean }) {
  const { rawText, ...fetchOptions } = options || {};
  const url = `${BACKEND_URL}${path}`;
  const token = getAuthToken();

  // 10-second timeout to prevent UI from appearing frozen
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 10000);

  try {
    const res = await fetch(url, {
      ...fetchOptions,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...(fetchOptions?.headers || {}),
      },
      signal: controller.signal,
    });
    clearTimeout(timeout);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      if (res.status === 401 || res.status === 403) {
        clearAuthToken();
        window.dispatchEvent(new Event('sentinel-auth-required'));
      }
      throw new Error(err.detail || res.statusText);
    }
    return rawText ? res.text() : res.json();
  } catch (err: any) {
    clearTimeout(timeout);
    if (err.name === 'AbortError') {
      console.warn(`API timeout (no backend?): ${path}`);
      // Return default values for specific endpoints to prevent crashes
      if (path === '/api/fx-rates') return { rates: { USD: 1 } };
      if (path === '/api/settings/currency-display') return { mode: 'usd' };
      throw new Error(`Request timeout after 10s: ${path}`);
    }
    throw err;
  }
}
