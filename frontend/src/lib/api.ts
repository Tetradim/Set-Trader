// Support both VITE_ (Vite) and REACT_APP_ (Create React App) prefixes
import { uiLog } from './clientLogger';

const BACKEND_URL = import.meta.env?.VITE_BACKEND_URL || import.meta.env?.REACT_APP_BACKEND_URL || '';
const AUTH_TOKEN_KEY = 'sentinel_auth_token';

export function formatApiErrorDetail(detail: unknown, fallback: string): string {
  if (typeof detail === 'string' && detail.trim()) return detail;

  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (typeof item === 'string') return item;
        if (!item || typeof item !== 'object') return '';

        const record = item as { loc?: unknown; msg?: unknown; message?: unknown };
        const message = typeof record.msg === 'string'
          ? record.msg
          : typeof record.message === 'string'
            ? record.message
            : '';
        if (!message) return '';

        const loc = Array.isArray(record.loc)
          ? record.loc.filter((part) => part !== 'body').join('.')
          : '';
        return loc ? `${loc}: ${message}` : message;
      })
      .filter(Boolean);
    if (messages.length) return messages.join('; ');
  }

  if (detail && typeof detail === 'object') {
    const record = detail as { detail?: unknown; msg?: unknown; message?: unknown };
    return formatApiErrorDetail(record.detail ?? record.msg ?? record.message, fallback);
  }

  return fallback;
}

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
  const method = fetchOptions.method || 'GET';
  const started = performance.now();
  uiLog.api('start', { path, method });

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
    const duration_ms = Math.round(performance.now() - started);

    if (!res.ok) {
      const err = await res.json().catch(() => ({ detail: res.statusText }));
      const message = formatApiErrorDetail(err.detail, res.statusText);
      uiLog.api('error', { path, method, status: res.status, duration_ms, message });
      if (res.status === 401 || res.status === 403) {
        clearAuthToken();
        window.dispatchEvent(new Event('sentinel-auth-required'));
      }
      throw new Error(message);
    }
    uiLog.api('success', { path, method, status: res.status, duration_ms });
    return rawText ? res.text() : res.json();
  } catch (err: any) {
    clearTimeout(timeout);
    const duration_ms = Math.round(performance.now() - started);
    if (err.name === 'AbortError') {
      uiLog.api('timeout', { path, method, duration_ms });
      // Return default values for specific endpoints to prevent crashes
      if (path === '/api/fx-rates') return { rates: { USD: 1 } };
      if (path === '/api/settings/currency-display') return { mode: 'usd' };
      throw new Error(`Request timeout after 10s: ${path}`);
    }
    const errorMessage = err?.message || String(err);
    if (err instanceof TypeError && errorMessage.toLowerCase().includes('fetch')) {
      const message = 'Backend is not reachable. Start Sentinel Pulse and try again.';
      uiLog.api('error', { path, method, duration_ms, message });
      throw new Error(message);
    }
    uiLog.api('error', { path, method, duration_ms, message: errorMessage });
    throw err;
  }
}
