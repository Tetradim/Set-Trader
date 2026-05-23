import { useMemo } from 'react';
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import {
  buildTickerChartData,
  getChartDomain,
  hasMeaningfulChartMovement,
  type PricePoint,
} from '@/lib/ticker-card-utils';

interface TickerSparklineProps {
  symbol: string;
  price: number;
  priceHistory: PricePoint[];
  isPositive: boolean;
}

export function TickerSparkline({ symbol, price, priceHistory, isPositive }: TickerSparklineProps) {
  const sparkColor = isPositive ? '#2dd4a0' : '#e03040';
  const chartData = useMemo(() => buildTickerChartData(priceHistory, price), [priceHistory, price]);
  const chartDomain = useMemo(() => getChartDomain(chartData), [chartData]);
  const hasChartMovement = useMemo(() => hasMeaningfulChartMovement(chartData), [chartData]);
  const chartGradientId = `chartGrad-${symbol.replace(/[^a-zA-Z0-9_-]/g, '-')}`;

  return (
    <div className={`sp-chart-container ${hasChartMovement ? '' : 'flat'}`}>
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={chartData} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <defs>
            <linearGradient id={chartGradientId} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={sparkColor} stopOpacity={0.3} />
              <stop offset="100%" stopColor={sparkColor} stopOpacity={0.05} />
            </linearGradient>
          </defs>
          <XAxis dataKey="time" hide />
          <YAxis domain={chartDomain} hide />
          <Tooltip
            contentStyle={{
              background: '#1a1a24',
              border: '1px solid rgba(220,168,40,0.3)',
              borderRadius: 4,
              fontSize: 11,
            }}
            labelStyle={{ display: 'none' }}
            formatter={(value: number) => [`$${value.toFixed(2)}`, 'Price']}
          />
          <Area
            type="monotone"
            dataKey="price"
            stroke={sparkColor}
            strokeWidth={1.5}
            fill={`url(#${chartGradientId})`}
            isAnimationActive={false}
            dot={false}
          />
        </AreaChart>
      </ResponsiveContainer>
      {!hasChartMovement && (
        <div className="sp-chart-flat-label">Live trace pending</div>
      )}
    </div>
  );
}
