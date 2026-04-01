/** Shared market detection and currency formatting utilities. */

export type MarketMeta = {
  flag: string;
  currency: string;
  currencySymbol: string;
};

export const MARKET_META: Record<string, MarketMeta> = {
  US:    { flag: '',    currency: 'USD', currencySymbol: '$'   },
  HK:    { flag: '🇭🇰', currency: 'HKD', currencySymbol: 'HK$' },
  AU:    { flag: '🇦🇺', currency: 'AUD', currencySymbol: 'A$'  },
  UK:    { flag: '🇬🇧', currency: 'GBP', currencySymbol: '£'   },
  CA:    { flag: '🇨🇦', currency: 'CAD', currencySymbol: 'C$'  },
  CN_SS: { flag: '🇨🇳', currency: 'CNY', currencySymbol: '¥'   },
  CN_SZ: { flag: '🇨🇳', currency: 'CNY', currencySymbol: '¥'   },
};

export function detectMarketCode(ticker: { market?: string; symbol: string }): string {
  if (ticker.market && ticker.market !== '') return ticker.market;
  const sym = ticker.symbol.toUpperCase();
  if (sym.endsWith('.HK')) return 'HK';
  if (sym.endsWith('.AX')) return 'AU';
  if (sym.endsWith('.L'))  return 'UK';
  if (sym.endsWith('.TO') || sym.endsWith('.V')) return 'CA';
  if (sym.endsWith('.SS')) return 'CN_SS';
  if (sym.endsWith('.SZ')) return 'CN_SZ';
  return 'US';
}

export function getMarketMeta(ticker: { market?: string; symbol: string }): MarketMeta {
  return MARKET_META[detectMarketCode(ticker)] ?? MARKET_META.US;
}

/**
 * Format a native-currency price value according to the display mode.
 * - 'native': show in the ticker's local currency (e.g. A$52.30)
 * - 'usd': convert to USD using the provided FX rates map
 */
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

/**
 * Return the secondary (opposite) currency label for a price.
 * Used to show "A$52.30" below a "$34.10" display, or vice-versa.
 */
export function formatPriceSecondary(
  amount: number,
  ticker: { market?: string; symbol: string },
  mode: 'usd' | 'native',
  fxRates: Record<string, number>
): string | null {
  const meta = getMarketMeta(ticker);
  if (meta.currency === 'USD') return null; // no secondary for US tickers
  if (mode === 'native') {
    // secondary: USD equivalent
    const rate = fxRates[meta.currency] ?? 1;
    return `$${(amount * rate).toFixed(2)}`;
  }
  // secondary: native amount
  return `${meta.currencySymbol}${amount.toFixed(2)}`;
}
