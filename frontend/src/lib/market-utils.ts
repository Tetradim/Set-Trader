/** Shared market detection and currency formatting utilities. */

export type MarketMeta = {
  flag: string;
  currency: string;
  currencySymbol: string;
};

export const MARKET_META: Record<string, MarketMeta> = {
  US: { flag: '🇺🇸', currency: 'USD', currencySymbol: '$' },
  CA: { flag: '🇨🇦', currency: 'CAD', currencySymbol: 'C$' },
  MX: { flag: '🇲🇽', currency: 'MXN', currencySymbol: 'MX$' },
  BR: { flag: '🇧🇷', currency: 'BRL', currencySymbol: 'R$' },
  UK: { flag: '🇬🇧', currency: 'GBP', currencySymbol: '£' },
  DE: { flag: '🇩🇪', currency: 'EUR', currencySymbol: '€' },
  FR: { flag: '🇫🇷', currency: 'EUR', currencySymbol: '€' },
  NL: { flag: '🇳🇱', currency: 'EUR', currencySymbol: '€' },
  ES: { flag: '🇪🇸', currency: 'EUR', currencySymbol: '€' },
  IT: { flag: '🇮🇹', currency: 'EUR', currencySymbol: '€' },
  CH: { flag: '🇨🇭', currency: 'CHF', currencySymbol: 'CHF' },
  SE: { flag: '🇸🇪', currency: 'SEK', currencySymbol: 'kr' },
  ZA: { flag: '🇿🇦', currency: 'ZAR', currencySymbol: 'R' },
  JP: { flag: '🇯🇵', currency: 'JPY', currencySymbol: '¥' },
  HK: { flag: '🇭🇰', currency: 'HKD', currencySymbol: 'HK$' },
  AU: { flag: '🇦🇺', currency: 'AUD', currencySymbol: 'A$' },
  CN_SS: { flag: '🇨🇳', currency: 'CNY', currencySymbol: '¥' },
  CN_SZ: { flag: '🇨🇳', currency: 'CNY', currencySymbol: '¥' },
  IN_NSE: { flag: '🇮🇳', currency: 'INR', currencySymbol: '₹' },
  IN_BSE: { flag: '🇮🇳', currency: 'INR', currencySymbol: '₹' },
  SG: { flag: '🇸🇬', currency: 'SGD', currencySymbol: 'S$' },
  KR: { flag: '🇰🇷', currency: 'KRW', currencySymbol: '₩' },
  TW: { flag: '🇹🇼', currency: 'TWD', currencySymbol: 'NT$' },
};

const SUFFIX_TO_MARKET: Array<[string, string]> = [
  ['.TWO', 'TW'],
  ['.HK', 'HK'],
  ['.AX', 'AU'],
  ['.TO', 'CA'],
  ['.V', 'CA'],
  ['.MX', 'MX'],
  ['.SA', 'BR'],
  ['.SS', 'CN_SS'],
  ['.SZ', 'CN_SZ'],
  ['.DE', 'DE'],
  ['.PA', 'FR'],
  ['.AS', 'NL'],
  ['.MC', 'ES'],
  ['.MI', 'IT'],
  ['.SW', 'CH'],
  ['.ST', 'SE'],
  ['.JO', 'ZA'],
  ['.NS', 'IN_NSE'],
  ['.BO', 'IN_BSE'],
  ['.SI', 'SG'],
  ['.KS', 'KR'],
  ['.KQ', 'KR'],
  ['.TW', 'TW'],
  ['.L', 'UK'],
  ['.T', 'JP'],
];

export function detectMarketCode(ticker: { market?: string; symbol: string }): string {
  if (ticker.market && ticker.market !== '') return ticker.market;
  const sym = ticker.symbol.toUpperCase();
  return SUFFIX_TO_MARKET.find(([suffix]) => sym.endsWith(suffix))?.[1] ?? 'US';
}

export function getMarketMeta(ticker: { market?: string; symbol: string }): MarketMeta {
  return MARKET_META[detectMarketCode(ticker)] ?? MARKET_META.US;
}

export function formatPrice(
  amount: number,
  ticker: { market?: string; symbol: string },
  mode: 'usd' | 'native',
  fxRates: Record<string, number>,
  decimals = 2
): string {
  const meta = getMarketMeta(ticker);
  if (meta.currency === 'USD') return `$${amount.toFixed(decimals)}`;
  if (mode === 'native') return `${meta.currencySymbol}${amount.toFixed(decimals)}`;
  const rate = fxRates[meta.currency] ?? 1;
  return `$${(amount * rate).toFixed(decimals)}`;
}

export function formatPriceSecondary(
  amount: number,
  ticker: { market?: string; symbol: string },
  mode: 'usd' | 'native',
  fxRates: Record<string, number>
): string | null {
  const meta = getMarketMeta(ticker);
  if (meta.currency === 'USD') return null;
  if (mode === 'native') {
    const rate = fxRates[meta.currency] ?? 1;
    return `$${(amount * rate).toFixed(2)}`;
  }
  return `${meta.currencySymbol}${amount.toFixed(2)}`;
}
