'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { format, formatDistanceToNow } from 'date-fns';
import SearchFilter from '@/components/SearchFilter';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Incident } from '@/lib/types';

type SyncStatusState = {
  status: 'idle' | 'syncing' | 'synced' | 'error' | 'never';
  last_sync_at: string | null;
  error: string | null;
};

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [syncStatus, setSyncStatus] = useState<SyncStatusState>({ status: 'idle', last_sync_at: null, error: null });
  const [syncing, setSyncing] = useState(false);

  const loadIncidents = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.incidents({ limit: 100 });
      setIncidents(data.incidents);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : 'Failed to load incidents');
    } finally {
      setLoading(false);
    }
  }, []);

  const loadSyncStatus = useCallback(async () => {
    try {
      const data = await api.syncStatus();
      const nextStatus: SyncStatusState['status'] = ['idle', 'syncing', 'synced', 'error', 'never'].includes(data.status)
        ? (data.status as SyncStatusState['status'])
        : data.last_sync_at
          ? 'synced'
          : 'never';

      setSyncStatus({
        status: nextStatus,
        last_sync_at: data.last_sync_at,
        error: data.error,
      });
    } catch (err: unknown) {
      setSyncStatus((prev) => ({
        ...prev,
        status: 'error',
        error: err instanceof Error ? err.message : 'Failed to load sync status',
      }));
    }
  }, []);

  useEffect(() => {
    loadIncidents();
  }, [loadIncidents]);

  useEffect(() => {
    loadSyncStatus();
  }, [loadSyncStatus]);

  const handleSync = async () => {
    setSyncing(true);
    setSyncStatus((prev) => ({ ...prev, status: 'syncing', error: null }));

    try {
      await api.forceSync();
      await Promise.all([loadSyncStatus(), loadIncidents()]);
    } catch (err: unknown) {
      setSyncStatus((prev) => ({
        ...prev,
        status: 'error',
        error: err instanceof Error ? err.message : 'Sync failed',
      }));
    } finally {
      setSyncing(false);
    }
  };

  const filtered = useMemo(() => {
    return incidents.filter((inc) => {
      if (query && !inc.title.toLowerCase().includes(query.toLowerCase()) && !inc.id.toLowerCase().includes(query.toLowerCase())) return false;
      if (severity && inc.severity !== severity) return false;
      if (status && inc.status !== status) return false;
      return true;
    });
  }, [incidents, query, severity, status]);

  const syncDotClass = syncStatus.status === 'synced'
    ? 'bg-green-500'
    : syncStatus.status === 'syncing'
      ? 'bg-yellow-400'
      : syncStatus.status === 'error'
        ? 'bg-red-500'
        : 'bg-gray-400';

  const syncLabel = syncStatus.status === 'error'
    ? `Sync error: ${syncStatus.error || 'Unknown error'}`
    : syncStatus.last_sync_at
      ? `Last synced: ${formatDistanceToNow(new Date(syncStatus.last_sync_at), { addSuffix: true })}`
      : 'Never synced';

  return (
    <div className="p-6 md:p-8 space-y-6">
      <h1 className="font-serif text-3xl">Incidents</h1>
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2 text-sm text-gray-600">
          <span className={`h-2.5 w-2.5 rounded-full ${syncDotClass}`} />
          <span>{syncing ? 'Syncing now...' : syncLabel}</span>
        </div>
        <button
          type="button"
          onClick={handleSync}
          disabled={syncing}
          className="inline-flex items-center justify-center gap-2 bg-coral text-white rounded-lg px-4 py-2 hover:bg-coral/90 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {syncing && <span className="h-4 w-4 animate-spin rounded-full border-2 border-white/30 border-t-white" />}
          <span>{syncing ? 'Syncing...' : 'Sync Now'}</span>
        </button>
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
