const BACKEND_URL = import.meta.env.REACT_APP_BACKEND_URL || '';

export async function apiFetch(path: string, options?: RequestInit & { rawText?: boolean }) {
  const { rawText, ...fetchOptions } = options || {};
  const url = `${BACKEND_URL}${path}`;
  const res = await fetch(url, {
    ...fetchOptions,
    headers: {
      'Content-Type': 'application/json',
      ...(fetchOptions?.headers || {}),
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || res.statusText);
  }
  return rawText ? res.text() : res.json();
}
