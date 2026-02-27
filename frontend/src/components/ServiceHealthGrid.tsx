import { Service } from '@/lib/types';
import clsx from 'clsx';

const statusConfig: Record<string, { bg: string; dot: string; label: string }> = {
  healthy: { bg: 'bg-green-50 border-green-200', dot: 'bg-green-500', label: 'Healthy' },
  degraded: { bg: 'bg-yellow-50 border-yellow-200', dot: 'bg-yellow-500', label: 'Degraded' },
  down: { bg: 'bg-red-50 border-red-200', dot: 'bg-red-500', label: 'Down' },
};

export default function ServiceHealthGrid({ services }: { services: Service[] }) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
      {services.map((s) => {
        const cfg = statusConfig[s.status] || statusConfig.healthy;
        return (
          <div key={s.name} className={clsx('rounded-lg border p-4', cfg.bg)}>
            <div className="flex items-center justify-between mb-2">
              <span className="font-medium text-sm text-gray-900">{s.name}</span>
              <span className="flex items-center gap-1.5 text-xs">
                <span className={clsx('w-2 h-2 rounded-full', cfg.dot)} />
                {cfg.label}
              </span>
            </div>
            <div className="flex gap-4 text-xs text-gray-500">
              <span>Latency: <strong className="text-gray-700">{s.latency_ms}ms</strong></span>
              <span>Errors: <strong className="text-gray-700">{s.error_rate}%</strong></span>
            </div>
            <div className="text-xs text-gray-400 mt-1">Team: {s.team} · Tier {s.tier}</div>
          </div>
        );
      })}
    </div>
  );
}
