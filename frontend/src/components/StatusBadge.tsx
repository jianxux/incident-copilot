import clsx from 'clsx';

const severityColors: Record<string, string> = {
  P1: 'bg-red-100 text-red-700 border-red-200',
  P2: 'bg-orange-100 text-orange-700 border-orange-200',
  P3: 'bg-yellow-100 text-yellow-700 border-yellow-200',
  P4: 'bg-green-100 text-green-700 border-green-200',
};

const statusColors: Record<string, string> = {
  open: 'bg-red-100 text-red-700 border-red-200',
  investigating: 'bg-amber-100 text-amber-700 border-amber-200',
  resolved: 'bg-green-100 text-green-700 border-green-200',
  closed: 'bg-gray-100 text-gray-600 border-gray-200',
};

export function SeverityBadge({ severity }: { severity: string }) {
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border', severityColors[severity] || 'bg-gray-100 text-gray-600')}>
      {severity}
    </span>
  );
}

export function StatusBadge({ status }: { status: string }) {
  return (
    <span className={clsx('inline-flex items-center px-2 py-0.5 rounded-full text-xs font-semibold border capitalize', statusColors[status] || 'bg-gray-100 text-gray-600')}>
      {status}
    </span>
  );
}
