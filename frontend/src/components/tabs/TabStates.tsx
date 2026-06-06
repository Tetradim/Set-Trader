import { AlertTriangle, RefreshCw } from 'lucide-react';

export function TabLoadingState({
  title = 'Loading tab',
  detail = 'Fetching the latest Sentinel Pulse data.',
}: {
  title?: string;
  detail?: string;
}) {
  return (
    <div
      className="glass flex min-h-48 flex-col items-center justify-center gap-3 rounded-xl border border-border bg-card/70 p-6 text-center"
      data-testid="tab-loading-state"
    >
      <RefreshCw className="h-7 w-7 animate-spin text-primary" />
      <div>
        <div className="text-sm font-semibold text-foreground">{title}</div>
        <div className="mt-1 text-xs text-muted-foreground">{detail}</div>
      </div>
    </div>
  );
}

export function TabErrorState({
  title = 'Unable to load tab',
  detail,
}: {
  title?: string;
  detail: string;
}) {
  return (
    <div
      className="glass flex min-h-40 flex-col items-center justify-center gap-3 rounded-xl border border-red-500/30 bg-red-500/10 p-6 text-center"
      data-testid="tab-error-state"
    >
      <AlertTriangle className="h-7 w-7 text-red-300" />
      <div>
        <div className="text-sm font-semibold text-red-100">{title}</div>
        <div className="mt-1 text-xs text-red-200/80">{detail}</div>
      </div>
    </div>
  );
}
