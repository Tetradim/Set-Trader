import type React from 'react';
import { ArrowDown, ArrowUp, SlidersHorizontal } from 'lucide-react';

type Props = {
  incText: string;
  decText: string;
  incStep: number;
  decStep: number;
  onIncTextChange: (value: string) => void;
  onDecTextChange: (value: string) => void;
  onIncCommit: () => void;
  onDecCommit: () => void;
};

export function StepSizeSection({
  incText,
  decText,
  incStep,
  decStep,
  onIncTextChange,
  onDecTextChange,
  onIncCommit,
  onDecCommit,
}: Props) {
  return (
    <section className="glass rounded-xl border border-border p-6 space-y-5">
      <div className="flex items-center gap-2 mb-2">
        <SlidersHorizontal size={18} className="text-accent" />
        <h3 className="text-sm font-bold text-foreground">Arrow Step Sizes</h3>
      </div>
      <p className="text-xs text-muted-foreground">
        Customize how much ticker-card input arrows change values.
      </p>
      <div className="grid grid-cols-2 gap-4">
        <StepInput
          testId="increment-step-input"
          label="Increase Step"
          value={incText}
          icon={<ArrowUp size={10} className="text-emerald-400" />}
          onChange={onIncTextChange}
          onBlur={onIncCommit}
        />
        <StepInput
          testId="decrement-step-input"
          label="Decrease Step"
          value={decText}
          icon={<ArrowDown size={10} className="text-red-400" />}
          onChange={onDecTextChange}
          onBlur={onDecCommit}
        />
      </div>
      <div className="rounded-lg bg-secondary/50 border border-border p-2 flex items-center gap-2 text-xs text-muted-foreground">
        <span className="font-mono text-primary">{incStep}</span>
        <ArrowUp size={10} className="text-emerald-400" /> /
        <span className="font-mono text-primary">{decStep}</span>
        <ArrowDown size={10} className="text-red-400" />
        <span>applies to all ticker card number inputs</span>
      </div>
    </section>
  );
}

function StepInput({
  testId,
  label,
  value,
  icon,
  onChange,
  onBlur,
}: {
  testId: string;
  label: string;
  value: string;
  icon: React.ReactNode;
  onChange: (value: string) => void;
  onBlur: () => void;
}) {
  return (
    <div>
      <label className="text-[10px] uppercase tracking-wider text-muted-foreground font-medium mb-1.5 flex items-center gap-1">
        {icon} {label}
      </label>
      <input
        data-testid={testId}
        type="text"
        inputMode="decimal"
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className="w-full bg-secondary border border-border rounded-lg px-3 py-2 text-sm font-mono focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2 focus:ring-offset-background text-foreground"
      />
    </div>
  );
}
