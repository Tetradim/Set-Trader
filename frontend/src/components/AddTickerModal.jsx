import React, { useState } from 'react';
import * as Dialog from '@radix-ui/react-dialog';
import { X, Plus, Loader2 } from 'lucide-react';

export const AddTickerModal = ({ onTickerAdded }) => {
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [formData, setFormData] = useState({ symbol: '', base_power: 100 });

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    try {
      const response = await fetch('http://localhost:8000/tickers', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(formData),
      });
      if (response.ok) {
        onTickerAdded();
        setOpen(false);
        setFormData({ symbol: '', base_power: 100 });
      }
    } catch (error) {
      console.error("Failed to add ticker:", error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog.Root open={open} onOpenChange={setOpen}>
      <Dialog.Trigger asChild>
        <button className="flex items-center gap-2 bg-primary text-primary-foreground px-4 py-2 rounded-lg hover:opacity-90 transition-all font-semibold shadow-sm">
          <Plus className="w-4 h-4" />
          Add Ticker
        </button>
      </Dialog.Trigger>
      
      <Dialog.Portal>
        <Dialog.Overlay className="fixed inset-0 bg-black/50 backdrop-blur-sm animate-in fade-in duration-200 z-50" />
        <Dialog.Content className="fixed top-[50%] left-[50%] translate-x-[-50%] translate-y-[-50%] w-[95vw] max-w-md bg-card border border-border p-6 rounded-xl shadow-2xl animate-in zoom-in-95 duration-200 z-50">
          <div className="flex justify-between items-center mb-4">
            <Dialog.Title className="text-xl font-bold">Monitor New Symbol</Dialog.Title>
            <Dialog.Close asChild>
              <button className="p-1 hover:bg-muted rounded-full"><X className="w-5 h-5" /></button>
            </Dialog.Close>
          </div>

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-1.5 block">Stock Symbol</label>
              <input 
                required
                className="w-full bg-background border border-border rounded-md px-3 py-2 uppercase placeholder:lowercase"
                placeholder="e.g. NVDA"
                value={formData.symbol}
                onChange={(e) => setFormData({...formData, symbol: e.target.value.toUpperCase()})}
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-1.5 block">Allocation ($)</label>
              <input 
                type="number"
                className="w-full bg-background border border-border rounded-md px-3 py-2"
                value={formData.base_power}
                onChange={(e) => setFormData({...formData, base_power: parseFloat(e.target.value)})}
              />
            </div>
            
            <button 
              type="submit" 
              disabled={loading}
              className="w-full bg-primary text-primary-foreground py-2.5 rounded-lg font-bold flex items-center justify-center gap-2 mt-2"
            >
              {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : "Start Tracking"}
            </button>
          </form>
        </Dialog.Content>
      </Dialog.Portal>
    </Dialog.Root>
  );
};