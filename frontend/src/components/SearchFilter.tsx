'use client';
import { Search } from 'lucide-react';

interface Props {
  query: string;
  onQueryChange: (q: string) => void;
  severity: string;
  onSeverityChange: (s: string) => void;
  status: string;
  onStatusChange: (s: string) => void;
}

export default function SearchFilter({ query, onQueryChange, severity, onSeverityChange, status, onStatusChange }: Props) {
  const selectClass = 'bg-white border border-gray-200 rounded-lg px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-coral/30 focus:border-coral';
  return (
    <div className="flex flex-col sm:flex-row gap-3">
      <div className="relative flex-1">
        <Search className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" size={16} />
        <input
          type="text"
          placeholder="Search incidents..."
          value={query}
          onChange={(e) => onQueryChange(e.target.value)}
          className="w-full pl-9 pr-3 py-2 bg-white border border-gray-200 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-coral/30 focus:border-coral"
        />
      </div>
      <select value={severity} onChange={(e) => onSeverityChange(e.target.value)} className={selectClass}>
        <option value="">All Severities</option>
        <option value="P1">P1 - Critical</option>
        <option value="P2">P2 - High</option>
        <option value="P3">P3 - Medium</option>
        <option value="P4">P4 - Low</option>
      </select>
      <select value={status} onChange={(e) => onStatusChange(e.target.value)} className={selectClass}>
        <option value="">All Statuses</option>
        <option value="open">Open</option>
        <option value="investigating">Investigating</option>
        <option value="resolved">Resolved</option>
        <option value="closed">Closed</option>
      </select>
    </div>
  );
}
