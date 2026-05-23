const BACKEND_URL = import.meta.env.VITE_BACKEND_URL || import.meta.env.REACT_APP_BACKEND_URL || '';
const AUTH_TOKEN_KEY = 'sentinel_auth_token';
const CLIENT_LOG_ENDPOINT = `${BACKEND_URL}/api/logs/client-events`;
const MAX_QUEUE = 250;
const FLUSH_INTERVAL_MS = 2000;

type ClientLogLevel = 'info' | 'warn' | 'error';

type ClientLogEvent = {
  type: string;
  level?: ClientLogLevel;
  message?: string;
  ts?: string;
  session_id?: string;
  url?: string;
  user_agent?: string;
  viewport?: string;
  [key: string]: unknown;
};

let installed = false;
let flushTimer: ReturnType<typeof setInterval> | null = null;
let sessionId = sessionStorage.getItem('sentinel_ui_session_id') || '';
const queue: ClientLogEvent[] = [];

if (!sessionId) {
  sessionId = crypto.randomUUID?.() || `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  sessionStorage.setItem('sentinel_ui_session_id', sessionId);
}

function authHeaders(): HeadersInit {
  const token = localStorage.getItem(AUTH_TOKEN_KEY);
  return {
    'Content-Type': 'application/json',
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

function currentContext() {
  return {
    ts: new Date().toISOString(),
    session_id: sessionId,
    url: window.location.href,
    user_agent: navigator.userAgent,
    viewport: `${window.innerWidth}x${window.innerHeight}`,
  };
}

function sanitize(value: unknown, depth = 0): unknown {
  if (depth > 4) return '[max-depth]';
  if (value == null || typeof value === 'number' || typeof value === 'boolean') return value;
  if (typeof value === 'string') return value.slice(0, 1000);
  if (Array.isArray(value)) return value.slice(0, 50).map((item) => sanitize(item, depth + 1));
  if (typeof value === 'object') {
    const clean: Record<string, unknown> = {};
    for (const [key, item] of Object.entries(value).slice(0, 80)) {
      const lowered = key.toLowerCase();
      if (
        lowered.includes('token') ||
        lowered.includes('password') ||
        lowered.includes('secret') ||
        lowered.includes('authorization') ||
        lowered.includes('api_key') ||
        lowered.includes('credential')
      ) {
        clean[key] = '[redacted]';
      } else {
        clean[key] = sanitize(item, depth + 1);
      }
    }
    return clean;
  }
  return String(value).slice(0, 1000);
}

function isSensitiveElement(el: Element) {
  const joined = [
    el.getAttribute('type'),
    el.getAttribute('name'),
    el.getAttribute('id'),
    el.getAttribute('aria-label'),
    el.getAttribute('data-testid'),
    el.getAttribute('placeholder'),
  ].filter(Boolean).join(' ').toLowerCase();
  return (
    joined.includes('password') ||
    joined.includes('token') ||
    joined.includes('secret') ||
    joined.includes('api') ||
    joined.includes('credential') ||
    joined.includes('authorization') ||
    joined.includes('bearer')
  );
}

function readElementValue(el: Element) {
  if (isSensitiveElement(el)) return '[redacted]';
  if (el instanceof HTMLInputElement) {
    if (el.type === 'checkbox' || el.type === 'radio') return el.checked;
    return el.value.slice(0, 300);
  }
  if (el instanceof HTMLTextAreaElement) return el.value.slice(0, 1000);
  if (el instanceof HTMLSelectElement) return el.value.slice(0, 300);
  return undefined;
}

function describeElement(target: EventTarget | null) {
  const el = target instanceof Element ? target : null;
  if (!el) return {};
  const input = el instanceof HTMLInputElement || el instanceof HTMLTextAreaElement || el instanceof HTMLSelectElement;
  const text = input ? '' : (el.textContent || '').replace(/\s+/g, ' ').trim().slice(0, 120);
  return {
    tag: el.tagName.toLowerCase(),
    type: el.getAttribute('type') || undefined,
    role: el.getAttribute('role') || undefined,
    test_id: el.getAttribute('data-testid') || undefined,
    aria_label: el.getAttribute('aria-label') || undefined,
    name: el.getAttribute('name') || undefined,
    id: el.id || undefined,
    classes: (el.getAttribute('class') || '').split(/\s+/).slice(0, 8).join(' ') || undefined,
    text: text || undefined,
    value: input ? readElementValue(el) : undefined,
    value_logged: input ? !isSensitiveElement(el) : undefined,
  };
}

function enqueue(event: ClientLogEvent) {
  queue.push(sanitize({ ...currentContext(), ...event }) as ClientLogEvent);
  while (queue.length > MAX_QUEUE) queue.shift();
}

export async function flushUiLogs() {
  if (!queue.length) return;
  const events = queue.splice(0, queue.length);
  try {
    await fetch(CLIENT_LOG_ENDPOINT, {
      method: 'POST',
      headers: authHeaders(),
      body: JSON.stringify({ events }),
      keepalive: true,
    });
  } catch {
    queue.unshift(...events.slice(-50));
  }
}

function flushUiLogsWithBeacon() {
  if (!queue.length) return;
  const events = queue.splice(0, queue.length);
  const payload = JSON.stringify({ events });
  if (navigator.sendBeacon) {
    const sent = navigator.sendBeacon(CLIENT_LOG_ENDPOINT, new Blob([payload], { type: 'application/json' }));
    if (sent) return;
  }
  fetch(CLIENT_LOG_ENDPOINT, { method: 'POST', headers: authHeaders(), body: payload, keepalive: true }).catch(() => {});
}

export const uiLog = {
  event: (type: string, detail: Record<string, unknown> = {}, level: ClientLogLevel = 'info') => enqueue({ type, level, ...detail }),
  error: (type: string, error: unknown, detail: Record<string, unknown> = {}) => enqueue({
    type,
    level: 'error',
    message: error instanceof Error ? error.message : String(error),
    stack: error instanceof Error ? error.stack : undefined,
    ...detail,
  }),
  api: (phase: 'start' | 'success' | 'error' | 'timeout', detail: Record<string, unknown>) => enqueue({
    type: `api.${phase}`,
    level: phase === 'error' || phase === 'timeout' ? 'error' : 'info',
    ...detail,
  }),
  ws: (phase: string, detail: Record<string, unknown> = {}, level: ClientLogLevel = 'info') => enqueue({
    type: `ws.${phase}`,
    level,
    ...detail,
  }),
  reactError: (error: Error, componentStack: string, label?: string) => enqueue({
    type: 'react.error_boundary',
    level: 'error',
    message: error.message,
    stack: error.stack,
    component_stack: componentStack,
    label,
  }),
  flush: flushUiLogs,
};

export function installUiLogging() {
  if (installed) return;
  installed = true;
  enqueue({ type: 'ui.session_start', level: 'info', message: 'Browser UI session started' });

  window.addEventListener('error', (event) => {
    uiLog.error('ui.uncaught_error', event.error || event.message, {
      source: event.filename,
      line: event.lineno,
      column: event.colno,
    });
  });

  window.addEventListener('unhandledrejection', (event) => {
    uiLog.error('ui.unhandled_rejection', event.reason);
  });

  document.addEventListener('click', (event) => {
    uiLog.event('ui.click', { element: describeElement(event.target) });
  }, true);

  document.addEventListener('submit', (event) => {
    uiLog.event('ui.submit', { element: describeElement(event.target) });
  }, true);

  document.addEventListener('change', (event) => {
    uiLog.event('ui.change', { element: describeElement(event.target) });
  }, true);

  document.addEventListener('visibilitychange', () => {
    uiLog.event('ui.visibility', { state: document.visibilityState });
    if (document.visibilityState === 'hidden') flushUiLogsWithBeacon();
  });

  window.addEventListener('beforeunload', flushUiLogsWithBeacon);
  flushTimer = setInterval(flushUiLogs, FLUSH_INTERVAL_MS);
}

export function uninstallUiLoggingForTest() {
  if (flushTimer) clearInterval(flushTimer);
  flushTimer = null;
  installed = false;
}
