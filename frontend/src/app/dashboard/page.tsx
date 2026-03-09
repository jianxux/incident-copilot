'use client';
import { useCallback, useEffect, useMemo, useState } from 'react';
import MetricCard from '@/components/MetricCard';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { api } from '@/lib/api';
import { Incident } from '@/lib/types';
import { format } from 'date-fns';
import Link from 'next/link';

type IncidentStats = {
  total: number;
  by_status: Record<string, number>;
  by_severity: Record<string, number>;
  mttr_hours: number;
  mtta_minutes: number;
  incidents_today: number;
  incidents_week: number;
};

const EMPTY_STATS: IncidentStats = {
  total: 0,
  by_status: {},
  by_severity: {},
  mttr_hours: 0,
  mtta_minutes: 0,
  incidents_today: 0,
  incidents_week: 0,
};

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [stats, setStats] = useState<IncidentStats>(EMPTY_STATS);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadDashboard = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [incidentRes, statsRes] = await Promise.all([
        api.incidents({ limit: 5 }),
        api.incidentStats(),
      ]);
      setIncidents(incidentRes.incidents);
      setStats(statsRes);
    } catch (err) {
      console.error('Failed to load dashboard data', err);
      setError('Failed to load dashboard data. Please try again.');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadDashboard();
  }, [loadDashboard]);

  const mttrValue = useMemo(() => {
    if (!Number.isFinite(stats.mttr_hours)) return 'N/A';
    if (stats.mttr_hours < 1) return `${Math.round(stats.mttr_hours * 60)} min`;
    const roundedHours = Math.round(stats.mttr_hours * 10) / 10;
    return `${roundedHours} hr`;
  }, [stats.mttr_hours]);

  const activeIncidents = (stats.by_status.triggered ?? 0) + (stats.by_status.acknowledged ?? 0);
  const resolutionRate = stats.total > 0 ? Math.round(((stats.by_status.resolved ?? 0) / stats.total) * 100) : 0;

  return (
    <div className="p-6 md:p-8 space-y-8">
      <h1 className="font-serif text-3xl">Dashboard</h1>

      {error && (
        <div className="rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700 flex items-center justify-between gap-4">
          <span>{error}</span>
          <button
            type="button"
            onClick={() => void loadDashboard()}
            className="rounded-md border border-red-300 px-3 py-1 text-xs font-medium hover:bg-red-100"
          >
            Retry
          </button>
        </div>
      )}

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          Array.from({ length: 4 }).map((_, index) => (
            <div key={index} className="bg-white rounded-xl border border-cream-dark shadow-sm p-5 animate-pulse">
              <div className="h-3 w-20 bg-cream-dark/70 rounded" />
              <div className="h-9 w-24 bg-cream-dark/70 rounded mt-3" />
              <div className="h-3 w-32 bg-cream-dark/70 rounded mt-3" />
            </div>
          ))
        ) : (
          <>
            <MetricCard label="MTTR" value={mttrValue} />
            <MetricCard label="Active Incidents" value={String(activeIncidents)} />
            <MetricCard label="Incidents (7d)" value={String(stats.incidents_week)} />
            <MetricCard label="Resolution Rate" value={`${resolutionRate}%`} />
          </>
        )}
      </div>

      {/* Recent Incidents */}
      <section>
        <div className="flex items-center justify-between mb-4">
          <h2 className="font-serif text-xl">Recent Incidents</h2>
          <Link href="/incidents" className="text-sm text-coral hover:underline">View all →</Link>
        </div>
        <div className="bg-white rounded-xl border border-cream-dark shadow-sm overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-cream-dark bg-cream">
                  <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Incident</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Service</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Severity</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Status</th>
                  <th className="text-left px-4 py-3 font-semibold text-gray-500 text-xs uppercase">Time</th>
                </tr>
              </thead>
              <tbody>
                {loading &&
                  Array.from({ length: 5 }).map((_, index) => (
                    <tr key={index} className="border-b border-cream-dark last:border-0">
                      <td className="px-4 py-3"><div className="h-4 w-40 bg-cream-dark/60 rounded animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-4 w-20 bg-cream-dark/60 rounded animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-5 w-16 bg-cream-dark/60 rounded-full animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-5 w-20 bg-cream-dark/60 rounded-full animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-4 w-24 bg-cream-dark/60 rounded animate-pulse" /></td>
                    </tr>
                  ))}
                {!loading && incidents.map((inc) => (
                  <tr key={inc.id} className="border-b border-cream-dark last:border-0 hover:bg-cream/50 transition-colors">
                    <td className="px-4 py-3">
                      <Link href={`/incidents/${inc.id}`} className="text-coral hover:underline font-medium">{inc.id}</Link>
                      <p className="text-gray-500 text-xs mt-0.5 truncate max-w-xs">{inc.title}</p>
                    </td>
                    <td className="px-4 py-3 text-gray-700">{inc.service}</td>
                    <td className="px-4 py-3"><SeverityBadge severity={inc.severity} /></td>
                    <td className="px-4 py-3"><StatusBadge status={inc.status} /></td>
                    <td className="px-4 py-3 text-gray-500 text-xs">{format(new Date(inc.triggered_at), 'MMM d, HH:mm')}</td>
                  </tr>
                ))}
                {!loading && incidents.length === 0 && (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-sm text-gray-500">
                      No incidents found.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
