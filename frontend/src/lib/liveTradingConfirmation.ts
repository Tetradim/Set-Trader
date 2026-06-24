export const LIVE_TRADING_CONFIRMATION = 'ENABLE LIVE TRADING';

export interface TradingModeState {
  simulate247: boolean;
  liveDuringMarketHours: boolean;
}

export interface SettingsModePayload {
  simulate_24_7?: boolean;
  live_during_market_hours?: boolean;
  paper_after_hours?: boolean;
  live_trading_confirmation?: string;
  live_trading_operator_secret?: string;
}

export function isLiveTradingMode(state: TradingModeState): boolean {
  return !state.simulate247 && state.liveDuringMarketHours;
}

export function isCandidateLiveTradingMode(
  current: TradingModeState,
  payload: SettingsModePayload,
): boolean {
  const simulate247 = payload.simulate_24_7 ?? current.simulate247;
  const liveDuringMarketHours = payload.live_during_market_hours ?? current.liveDuringMarketHours;
  return !simulate247 && liveDuringMarketHours;
}

export function needsLiveTradingConfirmation(
  current: TradingModeState,
  payload: SettingsModePayload,
): boolean {
  return !isLiveTradingMode(current) && isCandidateLiveTradingMode(current, payload);
}

export function addLiveTradingConfirmation(
  current: TradingModeState,
  payload: SettingsModePayload,
  confirmation: string | null,
  operatorSecret?: string | null,
): SettingsModePayload | null {
  if (!needsLiveTradingConfirmation(current, payload)) return payload;
  if (confirmation !== LIVE_TRADING_CONFIRMATION) return null;
  const trimmedOperatorSecret = operatorSecret?.trim();
  if (!trimmedOperatorSecret) return null;
  return {
    ...payload,
    live_trading_confirmation: LIVE_TRADING_CONFIRMATION,
    live_trading_operator_secret: trimmedOperatorSecret,
  };
}

export function requestLiveTradingPayload(
  current: TradingModeState,
  payload: SettingsModePayload,
  promptFn?: (message: string) => string | null,
): SettingsModePayload | null {
  if (!needsLiveTradingConfirmation(current, payload)) return payload;

  const ask = promptFn
    ?? (typeof window !== 'undefined' && typeof window.prompt === 'function'
      ? window.prompt.bind(window)
      : () => null);

  const confirmation = ask(
    `Type ${LIVE_TRADING_CONFIRMATION} to confirm live broker routing during market hours.`,
  );
  const operatorSecret = ask('Enter the live trading operator secret.');
  return addLiveTradingConfirmation(current, payload, confirmation, operatorSecret);
}
