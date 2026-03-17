import React, { useState, useEffect } from 'react';
import { Checkbox } from '@/components/ui/checkbox';
import { Plus, Minus } from 'lucide-react';

/* ========= useDecimalInput ========= */
export function useDecimalInput(externalValue: number, commit: (v: number) => void) {
  const [text, setText] = useState(String(externalValue));
  const [focused, setFocused] = useState(false);

  useEffect(() => {
    if (!focused) setText(String(externalValue));
  }, [externalValue, focused]);

  const handleChange = (raw: string) => {
    if (/^-?\d*\.?\d*$/.test(raw)) setText(raw);
  };

  const handleBlur = () => {
    setFocused(false);
    const num = parseFloat(text);
    if (!isNaN(num)) commit(num);
    else setText(String(externalValue));
  };

  return { text, setText, focused, setFocused, handleChange, handleBlur };
}

/* ========= ConfigSection ========= */
export function ConfigSection({
  title, icon: Icon, color, children,
}: {
  title: string; icon: any; color: string; children: React.ReactNode;
}) {
  return (
    <div>
      <p className={`text-[10px] uppercase tracking-wider font-semibold mb-2 flex items-center gap-1.5 ${color}`}>
        <Icon size={11} /> {title}
      </p>
      <div className="grid grid-cols-2 gap-2">{children}</div>
    </div>
  );
}

/* ========= OrderTypeToggle ========= */
export function OrderTypeToggle({
  value, onChange, testId,
}: {
  value: 'limit' | 'market'; onChange: (v: string) => void; testId: string;
}) {
  return (
    <div className="col-span-2 flex items-center gap-1 p-0.5 rounded-md bg-secondary/60 border border-border/40" data-testid={testId}>
      <button type="button" onClick={() => onChange('limit')}
        className={`flex-1 text-[10px] font-bold uppercase tracking-wider py-1 rounded transition-all ${
          value === 'limit' ? 'bg-primary/20 text-primary shadow-sm' : 'text-muted-foreground hover:text-foreground'
        }`} data-testid={`${testId}-limit`}>Limit</button>
      <button type="button" onClick={() => onChange('market')}
        className={`flex-1 text-[10px] font-bold uppercase tracking-wider py-1 rounded transition-all ${
          value === 'market' ? 'bg-amber-400/20 text-amber-400 shadow-sm' : 'text-muted-foreground hover:text-foreground'
        }`} data-testid={`${testId}-market`}>Market</button>
    </div>
  );
}

/* ========= OffsetInput ========= */
export function OffsetInput({
  label, value, isPercent, mode, onChange, incrementStep, decrementStep,
}: {
  label: string; value: number; isPercent: boolean;
  mode: 'buy' | 'sell' | 'stop';
  onChange: (v: number) => void;
  incrementStep: number; decrementStep: number;
}) {
  const isNegativePercent = isPercent && (mode === 'buy' || mode === 'stop');

  if (!isPercent) {
    const dec = useDecimalInput(Math.abs(value), (num) => onChange(Math.abs(num)));
    return (
      <div>
        <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
        <div className="flex items-center">
          <span className="flex items-center justify-center h-[26px] w-6 bg-emerald-500/15 text-emerald-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">$</span>
          <input type="text" inputMode="decimal" value={dec.text}
            onChange={(e) => dec.handleChange(e.target.value)}
            onFocus={() => dec.setFocused(true)} onBlur={dec.handleBlur}
            className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
            data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`} />
          <div className="flex flex-col h-[26px] shrink-0">
            <button onClick={() => onChange(parseFloat((value + incrementStep).toFixed(4)))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"><Plus size={8} /></button>
            <button onClick={() => onChange(parseFloat(Math.max(0, value - decrementStep).toFixed(4)))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"><Minus size={8} /></button>
          </div>
        </div>
        <p className="text-[8px] text-muted-foreground/50 mt-0.5">{mode === 'buy' ? 'Buy' : mode === 'sell' ? 'Sell' : 'Stop'} when price hits ${Math.abs(value).toFixed(2)}</p>
      </div>
    );
  }

  if (isNegativePercent) {
    const magnitude = Math.abs(value);
    const dec = useDecimalInput(magnitude, (num) => onChange(-Math.abs(num)));
    return (
      <div>
        <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
        <div className="flex items-center">
          <span className="flex items-center justify-center h-[26px] w-6 bg-red-500/15 text-red-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">&ndash;</span>
          <input type="text" inputMode="decimal" value={dec.text}
            onChange={(e) => dec.handleChange(e.target.value)}
            onFocus={() => dec.setFocused(true)} onBlur={dec.handleBlur}
            className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
            data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`} />
          <div className="flex flex-col h-[26px] shrink-0">
            <button onClick={() => onChange(-Math.max(0, magnitude - incrementStep))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors" title={`+${incrementStep}`}><Plus size={8} /></button>
            <button onClick={() => onChange(-(magnitude + decrementStep))}
              className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors" title={`-${decrementStep}`}><Minus size={8} /></button>
          </div>
        </div>
        <p className="text-[8px] text-muted-foreground/50 mt-0.5">{value}% from avg</p>
      </div>
    );
  }

  // Positive percent (sell)
  const dec = useDecimalInput(value, (num) => onChange(Math.abs(num)));
  return (
    <div>
      <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
      <div className="flex items-center">
        <span className="flex items-center justify-center h-[26px] w-6 bg-blue-500/15 text-blue-400 border border-border border-r-0 rounded-l text-xs font-bold shrink-0">+</span>
        <input type="text" inputMode="decimal" value={dec.text}
          onChange={(e) => dec.handleChange(e.target.value)}
          onFocus={() => dec.setFocused(true)} onBlur={dec.handleBlur}
          className="w-full h-[26px] bg-background border-y border-border px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground text-center"
          data-testid={`input-${label.toLowerCase().replace(/[\s()$%]/g, '-')}`} />
        <div className="flex flex-col h-[26px] shrink-0">
          <button onClick={() => onChange(parseFloat((value + incrementStep).toFixed(4)))}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"><Plus size={8} /></button>
          <button onClick={() => onChange(parseFloat(Math.max(0, value - decrementStep).toFixed(4)))}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"><Minus size={8} /></button>
        </div>
      </div>
      <p className="text-[8px] text-muted-foreground/50 mt-0.5">+{value}% from avg</p>
    </div>
  );
}

/* ========= SteppedInput ========= */
export function SteppedInput({
  label, value, onChange, min, max, incrementStep, decrementStep,
}: {
  label: string; value: number; onChange: (v: number) => void;
  min?: number; max?: number;
  incrementStep: number; decrementStep: number;
}) {
  const dec = useDecimalInput(value, (num) => {
    if (min !== undefined && num < min) return;
    if (max !== undefined && num > max) return;
    onChange(num);
  });

  const nudgeUp = () => {
    let next = value + incrementStep;
    if (max !== undefined) next = Math.min(next, max);
    onChange(parseFloat(next.toFixed(4)));
  };
  const nudgeDown = () => {
    let next = value - decrementStep;
    if (min !== undefined) next = Math.max(next, min);
    onChange(parseFloat(next.toFixed(4)));
  };

  return (
    <div>
      <label className="text-[10px] text-muted-foreground block mb-0.5">{label}</label>
      <div className="flex items-center">
        <input type="text" inputMode="decimal" value={dec.text}
          onChange={(e) => dec.handleChange(e.target.value)}
          onFocus={() => dec.setFocused(true)} onBlur={dec.handleBlur}
          className="w-full h-[26px] bg-background border border-border rounded-l px-2 text-xs font-mono focus:outline-none focus:ring-1 focus:ring-primary text-foreground [appearance:textfield] [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none" />
        <div className="flex flex-col h-[26px] shrink-0">
          <button onClick={nudgeUp}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 rounded-tr text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            title={`+${incrementStep}`}><Plus size={8} /></button>
          <button onClick={nudgeDown}
            className="flex items-center justify-center h-[13px] w-5 bg-secondary border border-border border-l-0 border-t-0 rounded-br text-muted-foreground hover:text-foreground hover:bg-primary/20 transition-colors"
            title={`-${decrementStep}`}><Minus size={8} /></button>
        </div>
      </div>
    </div>
  );
}

/* ========= ConfigToggle ========= */
export function ConfigToggle({
  label, checked, onChange, accent,
}: {
  label: string; checked: boolean; onChange: (v: boolean) => void; accent?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <Checkbox checked={checked} onCheckedChange={onChange}
        className={accent ? 'data-[state=checked]:bg-accent data-[state=checked]:border-accent' : 'data-[state=checked]:bg-primary data-[state=checked]:border-primary'} />
      <label className="text-[10px] text-muted-foreground cursor-pointer">{label}</label>
    </div>
  );
}
