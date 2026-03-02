'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { format, formatDistanceToNow } from 'date-fns';
import { RefreshCw } from 'lucide-react';
import SearchFilter from '@/components/SearchFilter';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Incident } from '@/lib/types';

type SyncState = { last_attempt: string | null; last_success: string | null; last_error: string | null; status: string };

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [syncState, setSyncState] = useState<SyncState | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadIncidents = useCallback(() => {
    setLoading(true);
    setError(null);
    api.incidents({ limit: 100 })
      .then((data) => { setIncidents(data.incidents); setLoading(false); })
      .catch((err) => { setError(err.message || 'Failed to load incidents'); setLoading(false); });
  }, []);

  const loadSyncStatus = useCallback(() => {
    api.syncStatus().then(setSyncState).catch(() => {});
  }, []);

  const handleForceSync = useCallback(async () => {
    setSyncing(true);
    try {
      await api.forceSync();
      // Wait a moment for sync to complete then reload
      await new Promise(r => setTimeout(r, 2000));
      loadIncidents();
      loadSyncStatus();
    } catch { /* ignore */ }
    setSyncing(false);
  }, [loadIncidents, loadSyncStatus]);

  useEffect(() => {
    loadIncidents();
    loadSyncStatus();
  }, [loadIncidents, loadSyncStatus]);

  const filtered = useMemo(() => {
    return incidents.filter((inc) => {
      if (query && !inc.title.toLowerCase().includes(query.toLowerCase()) && !inc.id.toLowerCase().includes(query.toLowerCase())) return false;
      if (severity && inc.severity !== severity) return false;
      if (status && inc.status !== status) return false;
      return true;
    });
  }, [incidents, query, severity, status]);

  const syncLabel = syncState?.status === 'synced'
    ? syncState.last_success
      ? `Synced ${formatDistanceToNow(new Date(syncState.last_success), { addSuffix: true })}`
      : 'Synced'
    : syncState?.status === 'in_progress'
    ? 'Syncing…'
    : syncState?.status === 'error'
    ? `Sync error: ${syncState.last_error?.slice(0, 60) || 'unknown'}`
    : syncState?.status === 'stale'
    ? 'Sync stale'
    : syncState?.status === 'never'
    ? 'Never synced'
    : null;

  const syncColor = syncState?.status === 'synced' ? 'text-green-600' : syncState?.status === 'error' ? 'text-red-500' : 'text-gray-500';

  return (
    <div className="p-6 md:p-8 space-y-6">
      <div className="flex items-center justify-between">
        <h1 className="font-serif text-3xl">Incidents</h1>
        <div className="flex items-center gap-3">
          {syncLabel && <span className={`text-xs ${syncColor}`}>{syncLabel}</span>}
          <button
            onClick={handleForceSync}
            disabled={syncing}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-lg border border-cream-dark bg-white hover:bg-cream transition-colors disabled:opacity-50"
          >
            <RefreshCw size={14} className={syncing ? 'animate-spin' : ''} />
            {syncing ? 'Syncing…' : 'Sync PagerDuty'}
          </button>
        </div>
      </div>
      <SearchFilter query={query} onQueryChange={setQuery} severity={severity} onSeverityChange={setSeverity} status={status} onStatusChange={setStatus} />

      <div className="bg-white rounded-xl border border-cream-dark shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          {loading ? (
            <div className="p-8 space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="animate-pulse flex gap-4">
                  <div className="h-4 bg-gray-200 rounded w-20" />
                  <div className="h-4 bg-gray-200 rounded w-64" />
                  <div className="h-4 bg-gray-200 rounded w-24" />
                  <div className="h-4 bg-gray-200 rounded w-16" />
                  <div className="h-4 bg-gray-200 rounded w-20" />
                  <div className="h-4 bg-gray-200 rounded w-32" />
                </div>
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center text-red-500">
              <p className="font-medium">Failed to load incidents</p>
              <p className="text-sm text-gray-400 mt-1">{error}</p>
            </div>
          ) : (
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
                      <Link href={`/incidents/${inc.id}`} className="text-coral hover:underline font-medium">{inc.id.slice(0, 8)}</Link>
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
          )}
        </div>
      </div>
    </div>
  );
}
