import type { Dispatch, SetStateAction } from 'react';
import { toast } from 'sonner';
import { TickerConfig, useStore } from '@/stores/useStore';
import { apiFetch } from '@/lib/api';
import { useWebSocket } from '@/hooks/useWebSocket';

type QuickEditState = { buy: boolean; sell: boolean; stop: boolean };

interface UseTickerCardActionsArgs {
  ticker: TickerConfig;
  isActive: boolean;
  pnl: number;
  confirmDelete: boolean;
  confirmTakeProfit: boolean;
  setConfirmDelete: Dispatch<SetStateAction<boolean>>;
  setConfirmTakeProfit: Dispatch<SetStateAction<boolean>>;
  setQuickEdit: Dispatch<SetStateAction<QuickEditState>>;
}

export function useTickerCardActions({
  ticker,
  isActive,
  pnl,
  confirmDelete,
  confirmTakeProfit,
  setConfirmDelete,
  setConfirmTakeProfit,
  setQuickEdit,
}: UseTickerCardActionsArgs) {
  const { send } = useWebSocket();

  const handleToggleEnabled = async () => {
    useStore.getState().updateTicker(ticker.symbol, { enabled: !isActive });
    try {
      const updated = await apiFetch(`/api/tickers/${encodeURIComponent(ticker.symbol)}`, {
        method: 'PUT',
        body: JSON.stringify({ enabled: !isActive }),
      });
      useStore.getState().updateTicker(ticker.symbol, updated);
    } catch (error: any) {
      useStore.getState().updateTicker(ticker.symbol, { enabled: isActive });
      toast.error(error.message || `Failed to ${isActive ? 'pause' : 'resume'} ${ticker.symbol}`);
    }
  };

  const handleDelete = async () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 4000);
      toast.warning(`Click remove again to delete ${ticker.symbol}`);
      return;
    }
    useStore.getState().removeTicker(ticker.symbol);
    try {
      await apiFetch(`/api/tickers/${encodeURIComponent(ticker.symbol)}`, { method: 'DELETE' });
      toast.success(`Removed ${ticker.symbol}`);
    } catch (error: any) {
      useStore.getState().addTicker(ticker);
      setConfirmDelete(false);
      toast.error(error.message || `Failed to remove ${ticker.symbol}`);
    }
  };

  const handleTakeProfit = () => {
    if (!confirmTakeProfit) {
      setConfirmTakeProfit(true);
      setTimeout(() => setConfirmTakeProfit(false), 4000);
      return;
    }
    send('TAKE_PROFIT', { symbol: ticker.symbol });
    setConfirmTakeProfit(false);
    toast.success(`Took profit for ${ticker.symbol}: $${pnl.toFixed(2)}`);
  };

  const saveQuickEdit = (field: string, value: number) => {
    send('UPDATE_TICKER', { symbol: ticker.symbol, [field]: value });
    setQuickEdit({ buy: false, sell: false, stop: false });
    toast.success(`${field} -> ${value}`);
  };

  return { handleToggleEnabled, handleDelete, handleTakeProfit, saveQuickEdit };
}
