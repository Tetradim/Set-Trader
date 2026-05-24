import { Wallet } from 'lucide-react';

type Props = {
  balanceText: string;
  balanceValue: number | null;
  allocated: number;
  onBalanceTextChange: (value: string) => void;
  onBalanceCommit: () => void;
};

export function AccountBalanceSection({
  balanceText,
  balanceValue,
  allocated,
  onBalanceTextChange,
  onBalanceCommit,
}: Props) {
  const total = balanceValue ?? 0;
  const available = total - allocated;

  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5">
      <div className="flex items-center gap-2 mb-2">
        <Wallet size={18} className="text-primary" />
        <h3 className="text-sm font-bold text-foreground">Account Balance</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Set your total account capital. This is the master balance from which buy power is allocated to individual tickers.
        Take Profit moves gains into your Cash Reserve.
      </p>
      <div>
        <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
          <Wallet size={10} className="text-primary" /> Total Account Balance ($)
        </label>
        <input
          data-testid="account-balance-input"
          type="text"
          inputMode="decimal"
          value={balanceText}
          onChange={(event) => onBalanceTextChange(event.target.value)}
          onBlur={onBalanceCommit}
          className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
          placeholder="e.g. 100000"
        />
        <p className="text-[10px] text-muted-foreground/60 mt-1">
          Your total trading capital. Allocate portions to each ticker via Buy Power.
        </p>
      </div>
      <div className="grid grid-cols-3 gap-3 text-center">
        <BalanceMetric label="Account" value={total} className="text-foreground" />
        <BalanceMetric label="Allocated" value={allocated} className="text-amber-400" />
        <BalanceMetric label="Available" value={available} className={available >= 0 ? 'text-emerald-400' : 'text-red-400'} />
      </div>
    </section>
  );
}

function BalanceMetric({ label, value, className }: { label: string; value: number; className: string }) {
  return (
    <div className="rounded-lg bg-secondary/50 border border-border p-3">
      <p className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium">{label}</p>
      <p className={`font-mono text-lg font-bold ${className}`}>
        ${value.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}
      </p>
    </div>
  );
}
