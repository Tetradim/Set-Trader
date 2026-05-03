import { useState, useEffect, useCallback } from 'react';
import { apiFetch } from '@/lib/api';

interface UseFetchState<T> {
  data: T | null;
  loading: boolean;
  error: string | null;
}

/**
 * Standardized hook for fetching data with loading and error states.
 * Replaces repetitive patterns like:
 *   const [data, setData] = useState<Type[]>([]);
 *   const [loading, setLoading] = useState(true);
 *   const [error, setError] = useState<string | null>(null);
 *   useEffect(() => { fetchData(); }, []);
 */
export function useFetch<T>(path: string, immediate = true) {
  const [data, setData] = useState<T | null>(null);
  const [loading, setLoading] = useState(immediate);
  const [error, setError] = useState<string | null>(null);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiFetch(path);
      setData(result);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unknown error');
    } finally {
      setLoading(false);
    }
  }, [path]);

  useEffect(() => {
    if (immediate) {
      fetchData();
    }
  }, [fetchData, immediate]);

  return { data, loading, error, refetch: fetchData };
}

/**
 * Hook for fetching with polling interval
 */
export function useFetchPoll<T>(path: string, intervalMs = 60000) {
  const { data, loading, error, refetch } = useFetch<T>(path, true);

  useEffect(() => {
    const timer = setInterval(refetch, intervalMs);
    return () => clearInterval(timer);
  }, [refetch, intervalMs]);

  return { data, loading, error, refetch };
}