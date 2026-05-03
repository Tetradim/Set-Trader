# Code Refactoring - Set-Trader Frontend

## Already Applied

### New Reusable Hooks (`src/lib/hooks.ts`)
Created a standardized `useFetch<T>` hook to replace repetitive fetching patterns:

```typescript
// Replace repetitive pattern (17+ occurrences):
const [data, setData] = useState<Type[]>([]);
const [loading, setLoading] = useState(true);
const [error, setError] = useState<string | null>(null);
useEffect(() => { fetchData(); }, []);

// With simple:
const { data, loading, error, refetch } = useFetch<Type[]>('/api/endpoint');
```

## Remaining Opportunities

### 1. Import Consolidation (Medium Impact)
- 17 files import `apiFetch` - could use the new hook
- 9 files have duplicate `import { useState, useEffect } from 'react'` - inconsistent ordering

### 2. Card Components (Low Impact)  
- 8 files import Card, CardContent, CardHeader, CardTitle - could create a reusable CardWrapper

### 3. Pre-existing TypeScript Issues (Out of Scope)
- Dashboard.tsx: Duplicate identifier errors (imports)
- AddTickerDialog.tsx, ConfigModal.tsx: Component prop type issues
- These existed before and are outside the Tab files scope

## How to Use the New Hook

```typescript
// In any tab component:
import { useFetch } from '@/lib/hooks';

function MyTab() {
  const { data, loading, error, refetch } = useFetch<MyType[]>('/api/data');
  
  if (loading) return <Spinner />;
  if (error) return <Error message={error} />;
  
  return <List items={data} onRefresh={refetch} />;
}
```