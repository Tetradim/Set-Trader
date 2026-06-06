import { FormEvent, ReactNode, useEffect, useState } from 'react';
import { apiFetch, clearAuthToken, getAuthToken, setAuthToken } from '@/lib/api';
import {
  clearRememberedCredentials,
  loadRememberedCredentials,
  saveRememberedCredentials,
} from '@/lib/rememberCredentials';

type AuthMode = 'loading' | 'setup' | 'login' | 'ready';

type AuthResponse = {
  access_token: string;
  username: string;
};

export function AuthGate({ children }: { children: ReactNode }) {
  const [initialCredentials] = useState(() => loadRememberedCredentials());
  const [mode, setMode] = useState<AuthMode>('loading');
  const [username, setUsername] = useState(initialCredentials.username || 'admin');
  const [password, setPassword] = useState(initialCredentials.password);
  const [rememberPassword, setRememberPassword] = useState(initialCredentials.remember);
  const [error, setError] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    let cancelled = false;

    async function checkAuth() {
      try {
        if (getAuthToken()) {
          await apiFetch('/api/auth/me');
          if (!cancelled) setMode('ready');
          return;
        }

        const status = await apiFetch('/api/auth/bootstrap-status');
        if (!cancelled) setMode(status.needs_bootstrap ? 'setup' : 'login');
      } catch {
        clearAuthToken();
        try {
          const status = await apiFetch('/api/auth/bootstrap-status');
          if (!cancelled) setMode(status.needs_bootstrap ? 'setup' : 'login');
        } catch {
          if (!cancelled) {
            setError('Backend is not reachable. Start Sentinel Pulse and try again.');
            setMode('login');
          }
        }
      }
    }

    function requireAuth() {
      clearAuthToken();
      setMode('login');
    }

    window.addEventListener('sentinel-auth-required', requireAuth);
    checkAuth();

    return () => {
      cancelled = true;
      window.removeEventListener('sentinel-auth-required', requireAuth);
    };
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setError('');
    setSubmitting(true);

    try {
      const path = mode === 'setup' ? '/api/auth/bootstrap' : '/api/auth/login';
      const payload = mode === 'setup'
        ? { username, password }
        : { username, password };
      const response: AuthResponse = await apiFetch(path, {
        method: 'POST',
        body: JSON.stringify(payload),
      });
      if (rememberPassword) {
        saveRememberedCredentials({ username, password });
      } else {
        clearRememberedCredentials();
      }
      setAuthToken(response.access_token);
      setPassword(rememberPassword ? password : '');
      setMode('ready');
    } catch (err: any) {
      setError(err.message || 'Authentication failed');
    } finally {
      setSubmitting(false);
    }
  }

  if (mode === 'ready') return <>{children}</>;

  return (
    <main className="min-h-screen bg-[#07080b] text-[#f0e8d0] flex items-center justify-center px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-[420px] border border-[rgba(180,130,10,0.28)] bg-[#0d0f14] p-6 shadow-2xl"
      >
        <div className="mb-6">
          <p className="text-xs uppercase tracking-[0.18em] text-[#c99a2e]">Sentinel Pulse</p>
          <h1 className="mt-2 text-2xl font-semibold">
            {mode === 'setup' ? 'Create Admin Account' : 'Sign In'}
          </h1>
        </div>

        <label className="mb-4 block text-sm">
          <span className="mb-1 block text-[#bdb4a0]">Username</span>
          <input
            className="w-full border border-[rgba(255,255,255,0.16)] bg-[#07080b] px-3 py-2 text-[#f0e8d0] outline-none focus:border-[#c99a2e]"
            value={username}
            onChange={(event) => setUsername(event.target.value)}
            autoComplete="username"
            required
          />
        </label>

        <label className="mb-4 block text-sm">
          <span className="mb-1 block text-[#bdb4a0]">Password</span>
          <input
            className="w-full border border-[rgba(255,255,255,0.16)] bg-[#07080b] px-3 py-2 text-[#f0e8d0] outline-none focus:border-[#c99a2e]"
            type="password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
            autoComplete={mode === 'setup' ? 'new-password' : 'current-password'}
            required
          />
        </label>

        <label className="mb-4 flex items-center gap-2 text-sm text-[#bdb4a0]">
          <input
            type="checkbox"
            checked={rememberPassword}
            onChange={(event) => setRememberPassword(event.target.checked)}
            className="h-4 w-4 accent-[#c99a2e]"
          />
          <span>Remember username and password</span>
        </label>

        {error && (
          <div className="mb-4 border border-[#7d2b2b] bg-[#210b0d] px-3 py-2 text-sm text-[#ffb9b9]">
            {error}
          </div>
        )}

        <button
          type="submit"
          disabled={submitting}
          className="w-full bg-[#c99a2e] px-4 py-2 font-semibold text-[#090909] disabled:cursor-not-allowed disabled:opacity-60"
        >
          {submitting ? 'Working...' : mode === 'setup' ? 'Create admin' : 'Sign in'}
        </button>
      </form>
    </main>
  );
}
