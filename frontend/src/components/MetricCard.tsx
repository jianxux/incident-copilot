import { TrendingDown, TrendingUp, Minus } from 'lucide-react';
import clsx from 'clsx';

interface Props {
  label: string;
  value: string;
  trend?: 'up' | 'down' | 'flat';
  trendLabel?: string;
  trendPositive?: boolean;
}

export default function MetricCard({ label, value, trend = 'flat', trendLabel, trendPositive }: Props) {
  const TrendIcon = trend === 'up' ? TrendingUp : trend === 'down' ? TrendingDown : Minus;
  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-5">
      <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">{label}</p>
      <p className="text-3xl font-serif text-gray-900 mt-1">{value}</p>
      {trendLabel && (
        <div className={clsx('flex items-center gap-1 mt-2 text-xs font-medium', trendPositive ? 'text-green-600' : 'text-red-600')}>
          <TrendIcon size={14} />
          {trendLabel}
        </div>
      )}
    </div>
  );
}
