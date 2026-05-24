import { useEffect, useState } from 'react';
import { toast } from 'sonner';
import { apiFetch } from '@/lib/api';
import { useStore } from '@/stores/useStore';
import { AccountBalanceSection } from '@/components/settings/AccountBalanceSection';
import { BrokerAllocationsSection } from '@/components/settings/BrokerAllocationsSection';
import { EdgeRetrySection, GlobalDrawdownSection } from '@/components/settings/RiskAndEdgeSections';
import { StepSizeSection } from '@/components/settings/StepSizeSection';
import { TelegramSettingsSection } from '@/components/settings/TelegramSettingsSection';
import { TradingModeSection } from '@/components/settings/TradingModeSection';

export function SettingsTab() {
  const [token, setToken] = useState('');
  const [chatIds, setChatIds] = useState<string[]>([]);
  const [newChatId, setNewChatId] = useState('');
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [tgConnected, setTgConnected] = useState(false);
  const [incStep, setIncStep] = useState(0.5);
  const [decStep, setDecStep] = useState(0.5);
  const [incText, setIncText] = useState('0.5');
  const [decText, setDecText] = useState('0.5');
  const [balanceText, setBalanceText] = useState('0');
  const [balanceValue, setBalanceValue] = useState<number | null>(null);
  const [allocated, setAllocated] = useState(0);
  const [drawdownEnabled, setDrawdownEnabled] = useState(false);
  const [drawdownLimitText, setDrawdownLimitText] = useState('3');
  const [drawdownLimitValue, setDrawdownLimitValue] = useState(3);
  const [drawdownType, setDrawdownType] = useState<'percent' | 'cash'>('percent');
  const [edgeRetryAttempts, setEdgeRetryAttempts] = useState(10);
  const [edgeRetryAttemptsText, setEdgeRetryAttemptsText] = useState('10');

  useEffect(() => {
    apiFetch('/api/settings')
      .then((data) => {
        setToken(data.telegram?.bot_token || '');
        setChatIds(data.telegram?.chat_ids || []);
        setTgConnected(data.telegram_connected || false);
        setIncStep(data.increment_step ?? 0.5);
        setDecStep(data.decrement_step ?? 0.5);
        setIncText(String(data.increment_step ?? 0.5));
        setDecText(String(data.decrement_step ?? 0.5));
        setAllocated(data.allocated ?? 0);
        setEdgeRetryAttempts(data.edge_retry_max_attempts ?? 10);
        setEdgeRetryAttemptsText(String(data.edge_retry_max_attempts ?? 10));
        if (data.account_balance !== undefined && data.account_balance !== null) {
          setBalanceValue(data.account_balance);
          setBalanceText(String(data.account_balance));
          useStore.getState().setAccountBalance(data.account_balance, data.allocated ?? 0, data.available ?? 0);
        }
        useStore.getState().setSimulate247(data.simulate_24_7 || false);
        useStore.getState().setLiveDuringMarketHours(data.live_during_market_hours || false);
        useStore.getState().setPaperAfterHours(data.paper_after_hours || false);
        useStore.getState().setIncrementStep(data.increment_step ?? 0.5);
        useStore.getState().setDecrementStep(data.decrement_step ?? 0.5);
        if (data.global_daily_drawdown !== undefined) {
          const settings = data.global_daily_drawdown;
          setDrawdownEnabled(settings.enabled ?? false);
          setDrawdownLimitValue(settings.limit ?? 3);
          setDrawdownLimitText(String(settings.limit ?? 3));
          setDrawdownType(settings.type ?? 'percent');
          useStore.getState().setGlobalDailyDrawdown(settings.enabled ?? false, settings.limit ?? 3, settings.type ?? 'percent');
        }
      })
      .catch(() => {});
  }, []);

  const commitBalance = () => {
    const value = parseFloat(balanceText);
    if (!Number.isNaN(value) && value >= 0) {
      setBalanceValue(value);
    } else {
      setBalanceText(String(balanceValue ?? 0));
    }
  };

  const commitDrawdownLimit = () => {
    const value = parseFloat(drawdownLimitText);
    if (!Number.isNaN(value) && value > 0) {
      setDrawdownLimitValue(value);
    } else {
      setDrawdownLimitText(String(drawdownLimitValue));
    }
  };

  const commitEdgeRetryAttempts = () => {
    const value = parseInt(edgeRetryAttemptsText, 10);
    if (!Number.isNaN(value) && value >= 0 && value <= 100) {
      setEdgeRetryAttempts(value);
    } else {
      setEdgeRetryAttemptsText(String(edgeRetryAttempts));
    }
  };

  const commitIncStep = () => {
    const value = parseFloat(incText);
    if (!Number.isNaN(value) && value >= 0.01) {
      setIncStep(value);
    } else {
      setIncText(String(incStep));
    }
  };

  const commitDecStep = () => {
    const value = parseFloat(decText);
    if (!Number.isNaN(value) && value >= 0.01) {
      setDecStep(value);
    } else {
      setDecText(String(decStep));
    }
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const balanceToSave = balanceValue ?? parseFloat(balanceText) ?? 0;
      const res = await apiFetch('/api/settings', {
        method: 'POST',
        body: JSON.stringify({
          telegram: { bot_token: token, chat_ids: chatIds },
          simulate_24_7: useStore.getState().simulate247,
          increment_step: incStep,
          decrement_step: decStep,
          account_balance: balanceToSave,
          global_daily_drawdown: {
            enabled: drawdownEnabled,
            limit: drawdownLimitValue,
            type: drawdownType,
          },
          edge_retry_max_attempts: edgeRetryAttempts,
        }),
      });
      setBalanceValue(balanceToSave);
      setBalanceText(String(balanceToSave));
      useStore.getState().setIncrementStep(incStep);
      useStore.getState().setDecrementStep(decStep);
      useStore.getState().setAccountBalance(balanceToSave, allocated, balanceToSave - allocated);
      useStore.getState().setGlobalDailyDrawdown(drawdownEnabled, drawdownLimitValue, drawdownType);
      setTgConnected(res.telegram_running || false);
      if (res.telegram_running) {
        toast.success('Settings saved. Telegram bot connected!');
      } else if (token) {
        toast.error('Settings saved but Telegram failed to connect. Check your token.');
      } else {
        toast.success('Settings saved. Telegram disconnected.');
      }
    } catch (error: any) {
      toast.error(error.message || 'Save failed');
    } finally {
      setSaving(false);
    }
  };

  const handleTestAlert = async () => {
    setTesting(true);
    try {
      await apiFetch('/api/settings/telegram/test', { method: 'POST' });
      toast.success('Test alert sent to all chat IDs!');
    } catch (error: any) {
      toast.error(error.message || 'Test failed');
    } finally {
      setTesting(false);
    }
  };

  const addChatId = () => {
    const id = newChatId.trim();
    if (id && !chatIds.includes(id)) {
      setChatIds([...chatIds, id]);
      setNewChatId('');
    }
  };

  return (
    <div className="max-w-2xl space-y-8" data-testid="settings-tab">
      <AccountBalanceSection
        balanceText={balanceText}
        balanceValue={balanceValue}
        allocated={allocated}
        onBalanceTextChange={(value) => /^\d*\.?\d*$/.test(value) && setBalanceText(value)}
        onBalanceCommit={commitBalance}
      />
      <TradingModeSection />
      <GlobalDrawdownSection
        enabled={drawdownEnabled}
        limitText={drawdownLimitText}
        limitValue={drawdownLimitValue}
        type={drawdownType}
        onEnabledChange={setDrawdownEnabled}
        onLimitTextChange={(value) => /^\d*\.?\d*$/.test(value) && setDrawdownLimitText(value)}
        onLimitCommit={commitDrawdownLimit}
        onTypeChange={setDrawdownType}
      />
      <EdgeRetrySection
        attemptsText={edgeRetryAttemptsText}
        onAttemptsTextChange={(value) => /^\d*$/.test(value) && setEdgeRetryAttemptsText(value)}
        onAttemptsCommit={commitEdgeRetryAttempts}
      />
      <BrokerAllocationsSection />
      <StepSizeSection
        incText={incText}
        decText={decText}
        incStep={incStep}
        decStep={decStep}
        onIncTextChange={(value) => /^\d*\.?\d*$/.test(value) && setIncText(value)}
        onDecTextChange={(value) => /^\d*\.?\d*$/.test(value) && setDecText(value)}
        onIncCommit={commitIncStep}
        onDecCommit={commitDecStep}
      />
      <TelegramSettingsSection
        token={token}
        chatIds={chatIds}
        newChatId={newChatId}
        connected={tgConnected}
        saving={saving}
        testing={testing}
        onTokenChange={setToken}
        onNewChatIdChange={setNewChatId}
        onAddChatId={addChatId}
        onRemoveChatId={(id) => setChatIds(chatIds.filter((chatId) => chatId !== id))}
        onSave={handleSave}
        onTestAlert={handleTestAlert}
      />
    </div>
  );
}
