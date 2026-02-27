'use client';
import { useState, useMemo } from 'react';
import Link from 'next/link';
import { format } from 'date-fns';
import SearchFilter from '@/components/SearchFilter';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { mockIncidents } from '@/lib/mock-data';

export default function IncidentsPage() {
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');

  const filtered = useMemo(() => {
    return mockIncidents.filter((inc) => {
      if (query && !inc.title.toLowerCase().includes(query.toLowerCase()) && !inc.id.toLowerCase().includes(query.toLowerCase())) return false;
      if (severity && inc.severity !== severity) return false;
      if (status && inc.status !== status) return false;
      return true;
    });
  }, [query, severity, status]);

  return (
    <div className="p-6 md:p-8 space-y-6">
      <h1 className="font-serif text-3xl">Incidents</h1>
      <SearchFilter query={query} onQueryChange={setQuery} severity={severity} onSeverityChange={setSeverity} status={status} onStatusChange={setStatus} />

      <div className="bg-white rounded-xl border border-cream-dark shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-cream-dark bg-cream">
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">ID</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Title</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Service</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Severity</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Status</th>
                <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Triggered</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((inc) => (
                <tr key={inc.id} className="border-b border-cream-dark last:border-0 hover:bg-cream/50 transition-colors">
                  <td className="px-4 py-3">
                    <Link href={`/incidents/${inc.id}`} className="text-coral hover:underline font-medium">{inc.id}</Link>
                  </td>
                  <td className="px-4 py-3 text-gray-800 max-w-sm truncate">{inc.title}</td>
                  <td className="px-4 py-3 text-gray-600">{inc.service}</td>
                  <td className="px-4 py-3"><SeverityBadge severity={inc.severity} /></td>
                  <td className="px-4 py-3"><StatusBadge status={inc.status} /></td>
                  <td className="px-4 py-3 text-gray-500 text-xs whitespace-nowrap">{format(new Date(inc.triggered_at), 'MMM d, yyyy HH:mm')}</td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr><td colSpan={6} className="px-4 py-8 text-center text-gray-400">No incidents match your filters.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}
