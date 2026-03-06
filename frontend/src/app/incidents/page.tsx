'use client';
import { useState, useEffect, useMemo, useCallback } from 'react';
import Link from 'next/link';
import { format, formatDistanceToNow } from 'date-fns';
import SearchFilter from '@/components/SearchFilter';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Incident, PdSyncStatus } from '@/lib/types';

export default function IncidentsPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [query, setQuery] = useState('');
  const [severity, setSeverity] = useState('');
  const [status, setStatus] = useState('');
  const [syncStatus, setSyncStatus] = useState<PdSyncStatus | null>(null);
  const [syncing, setSyncing] = useState(false);

  const loadIncidents = () => api.incidents({ limit: 100 });

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    loadIncidents()
      .then((data) => {
        if (!cancelled) {
          setIncidents(data.incidents);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Failed to load incidents');
          setLoading(false);
        }
      });

    api.syncStatus()
      .then((data) => {
        if (!cancelled) {
          setSyncStatus(data);
        }
      })
      .catch(() => {
        // Sync status is optional UI metadata; keep page usable on failures.
      });

    return () => { cancelled = true; };
  }, []);

  const handleForceSync = async () => {
    setSyncing(true);
    try {
      await api.forceSync();
      const [incidentsData, syncData] = await Promise.all([
        loadIncidents(),
        api.syncStatus(),
      ]);
      setIncidents(incidentsData.incidents);
      setSyncStatus(syncData);
    } catch {
      // Keep existing UI state if sync call fails.
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

  return (
    <div className="p-6 md:p-8 space-y-6">
      <h1 className="font-serif text-3xl">Incidents</h1>
      <div className="bg-cream border border-cream-dark rounded-lg px-4 py-2 text-sm flex items-center justify-between gap-3">
        <div className="min-w-0">
          {syncStatus?.status === 'synced' && (
            <p className="text-gray-700 truncate">
              <span className="text-green-600">●</span> Synced
              {syncStatus.last_success ? ` ${formatDistanceToNow(new Date(syncStatus.last_success), { addSuffix: true })}` : ''}
            </p>
          )}
          {syncStatus?.status === 'syncing' && (
            <p className="text-amber-600 truncate"><span className="inline-block animate-spin mr-1">↻</span>Syncing...</p>
          )}
          {syncStatus?.status === 'stale' && (
            <p className="text-gray-700 truncate">
              <span className="text-amber-600">●</span> Sync stale
              {syncStatus.last_success ? ` ${formatDistanceToNow(new Date(syncStatus.last_success), { addSuffix: true })}` : ''}
            </p>
          )}
          {syncStatus?.status === 'error' && (
            <p className="text-gray-700 truncate" title={syncStatus.last_error || 'Unknown sync error'}>
              <span className="text-red-600">●</span> Sync failed
              {syncStatus.last_error ? <span className="text-red-500">: {syncStatus.last_error}</span> : ''}
            </p>
          )}
          {(!syncStatus || syncStatus.status === 'never') && (
            <p className="text-gray-600 truncate"><span className="text-gray-400">●</span> Never synced</p>
          )}
        </div>
        <button
          type="button"
          onClick={handleForceSync}
          disabled={syncing}
          className="bg-coral text-white rounded-md px-3 py-1.5 text-sm hover:bg-coral/90 disabled:opacity-60 disabled:cursor-not-allowed"
        >
          {syncing ? 'Syncing...' : 'Sync Now'}
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
