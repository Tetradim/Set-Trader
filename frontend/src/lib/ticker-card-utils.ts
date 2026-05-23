export type PricePoint = {
  time: number;
  price: number;
};

export type ChartPoint = {
  time: number;
  price: number;
};

export type ResizeDirection = 'n' | 's' | 'e' | 'w' | 'ne' | 'nw' | 'se' | 'sw';

export type ResizeInput = {
  direction: ResizeDirection;
  startWidth: number;
  startHeight: number;
  deltaX: number;
  deltaY: number;
  minWidth: number;
  minHeight: number;
  snap: boolean;
  snapGrid: number;
};

export type ResizeState = {
  width: number;
  height: number;
};

export const TICKER_CARD_MIN_WIDTH = 200;
export const TICKER_CARD_MIN_HEIGHT = 215;
export const TICKER_CARD_SNAP_GRID = 10;

export const RESIZE_HANDLES: Array<{
  direction: ResizeDirection;
  label: string;
  className: string;
}> = [
  { direction: 'nw', label: 'Resize northwest', className: 'sp-resize-handle sp-resize-nw' },
  { direction: 'n', label: 'Resize north', className: 'sp-resize-handle sp-resize-n' },
  { direction: 'ne', label: 'Resize northeast', className: 'sp-resize-handle sp-resize-ne' },
  { direction: 'e', label: 'Resize east', className: 'sp-resize-handle sp-resize-e' },
  { direction: 'se', label: 'Resize southeast', className: 'sp-resize-handle sp-resize-se' },
  { direction: 's', label: 'Resize south', className: 'sp-resize-handle sp-resize-s' },
  { direction: 'sw', label: 'Resize southwest', className: 'sp-resize-handle sp-resize-sw' },
  { direction: 'w', label: 'Resize west', className: 'sp-resize-handle sp-resize-w' },
];

export function buildTickerChartData(
  priceHistory: PricePoint[],
  currentPrice: number,
  now = Date.now(),
): ChartPoint[] {
  const cleanHistory = priceHistory
    .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.price) && point.price > 0)
    .slice(-120);

  if (cleanHistory.length >= 2) {
    return cleanHistory;
  }

  const fallbackPrice = cleanHistory[0]?.price ?? (Number.isFinite(currentPrice) && currentPrice > 0 ? currentPrice : 0);
  const latestPrice = Number.isFinite(currentPrice) && currentPrice > 0 ? currentPrice : fallbackPrice;
  const startTime = cleanHistory[0]?.time ?? now - 60_000;
  const endTime = Math.max(now, startTime + 1);

  return [
    { time: startTime, price: fallbackPrice },
    { time: endTime, price: latestPrice },
  ];
}

export function hasMeaningfulChartMovement(chartData: ChartPoint[]): boolean {
  if (chartData.length < 2) return false;
  const first = chartData[0]?.price ?? 0;
  return chartData.some((point) => Math.abs(point.price - first) > 0.0001);
}

export function getChartDomain(chartData: ChartPoint[]): [number, number] {
  if (chartData.length === 0) return [0, 1];

  let min = Number.POSITIVE_INFINITY;
  let max = Number.NEGATIVE_INFINITY;

  for (const point of chartData) {
    min = Math.min(min, point.price);
    max = Math.max(max, point.price);
  }

  if (!Number.isFinite(min) || !Number.isFinite(max)) return [0, 1];

  const padding = (max - min) * 0.1 || Math.max(max * 0.01, 1);
  return [min - padding, max + padding];
}

export function computeResizeState(input: ResizeInput): ResizeState {
  const changesWidth = input.direction.includes('w') || input.direction.includes('e');
  const changesHeight = input.direction.includes('n') || input.direction.includes('s');
  const horizontalDelta = input.direction.includes('w') ? -input.deltaX : input.direction.includes('e') ? input.deltaX : 0;
  const verticalDelta = input.direction.includes('n') ? -input.deltaY : input.direction.includes('s') ? input.deltaY : 0;

  const rawWidth = Math.max(input.minWidth, input.startWidth + horizontalDelta);
  const rawHeight = Math.max(input.minHeight, input.startHeight + verticalDelta);

  return {
    width: input.snap && changesWidth ? snapToGrid(rawWidth, input.snapGrid, input.minWidth) : rawWidth,
    height: input.snap && changesHeight ? snapToGrid(rawHeight, input.snapGrid, input.minHeight) : rawHeight,
  };
}

function snapToGrid(value: number, grid: number, minimum: number): number {
  if (grid <= 0) return Math.max(minimum, value);
  return Math.max(minimum, Math.round(value / grid) * grid);
}
