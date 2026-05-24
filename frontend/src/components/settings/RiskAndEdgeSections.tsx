import type React from 'react';
import { CircuitBoard, DollarSign, Percent, Plug } from 'lucide-react';
import { Switch } from '@/components/ui/switch';

type DrawdownType = 'percent' | 'cash';

type DrawdownProps = {
  enabled: boolean;
  limitText: string;
  limitValue: number;
  type: DrawdownType;
  onEnabledChange: (value: boolean) => void;
  onLimitTextChange: (value: string) => void;
  onLimitCommit: () => void;
  onTypeChange: (value: DrawdownType) => void;
};

export function GlobalDrawdownSection({
  enabled,
  limitText,
  limitValue,
  type,
  onEnabledChange,
  onLimitTextChange,
  onLimitCommit,
  onTypeChange,
}: DrawdownProps) {
  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          <CircuitBoard size={18} className="text-red-400" />
          <h3 className="text-sm font-bold text-foreground">Global Daily Drawdown Limit</h3>
        </div>
        <Switch data-testid="drawdown-toggle" checked={enabled} onCheckedChange={onEnabledChange} className="data-[state=checked]:bg-red-500" />
      </div>
      <p className="text-xs text-muted-foreground">
        Portfolio-level circuit breaker. If total daily losses exceed this limit, all bots pause for the rest of the day.
      </p>
      {enabled && (
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
              {type === 'percent' ? <Percent size={10} className="text-amber-400" /> : <DollarSign size={10} className="text-emerald-400" />}
              {type === 'percent' ? 'Limit (%)' : 'Limit ($)'}
            </label>
            <input
              data-testid="drawdown-limit-input"
              type="text"
              inputMode="decimal"
              value={limitText}
              onChange={(event) => onLimitTextChange(event.target.value)}
              onBlur={onLimitCommit}
              className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
              placeholder={type === 'percent' ? 'e.g. 3' : 'e.g. 3000'}
            />
          </div>
          <div>
            <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
              <CircuitBoard size={10} className="text-red-400" /> Type
            </label>
            <div className="flex rounded-lg overflow-hidden border border-border">
              <TypeButton active={type === 'percent'} onClick={() => onTypeChange('percent')} icon={<Percent size={12} />} label="Percent" />
              <TypeButton active={type === 'cash'} onClick={() => onTypeChange('cash')} icon={<DollarSign size={12} />} label="Cash" />
            </div>
          </div>
        </div>
      )}
      {enabled && (
        <div className="rounded-lg bg-red-500/10 border border-red-500/20 p-3">
          <p className="text-xs text-red-400 font-medium">
            All bots pause automatically when daily P&L drops below{' '}
            {type === 'percent' ? `${limitValue}% of account balance` : `$${limitValue.toLocaleString()}`}.
          </p>
        </div>
      )}
    </section>
  );
}

function TypeButton({ active, onClick, icon, label }: { active: boolean; onClick: () => void; icon: React.ReactNode; label: string }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className={`flex-1 py-2 text-xs font-medium flex items-center justify-center gap-1 ${
        active ? 'bg-amber-500/20 text-amber-400' : 'bg-secondary text-muted-foreground hover:text-foreground'
      }`}
    >
      {icon} {label}
    </button>
  );
}

type EdgeRetryProps = {
  attemptsText: string;
  onAttemptsTextChange: (value: string) => void;
  onAttemptsCommit: () => void;
};

export function EdgeRetrySection({ attemptsText, onAttemptsTextChange, onAttemptsCommit }: EdgeRetryProps) {
  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5">
      <div className="flex items-center gap-2 mb-2">
        <Plug size={18} className="text-primary" />
        <h3 className="text-sm font-bold text-foreground">Sentinel Edge Retry Policy</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Limits exponential backoff retries after Edge has been connected and then stops responding. If Edge is absent at Pulse startup, Pulse starts normally.
      </p>
      <div>
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
          <Plug size={10} className="text-primary" /> Backoff Attempts
        </label>
        <input
          data-testid="edge-retry-attempts-input"
          type="text"
          inputMode="numeric"
          value={attemptsText}
          onChange={(event) => onAttemptsTextChange(event.target.value)}
          onBlur={onAttemptsCommit}
          className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
          placeholder="10"
        />
        <p className="text-[10px] text-muted-foreground/60 mt-1">
          Default is 10. Use 0 to stop retrying after the first post-connection Edge failure.
        </p>
      </div>
    </section>
  );
}
