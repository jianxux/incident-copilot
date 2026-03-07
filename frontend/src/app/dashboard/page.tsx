'use client';
import { useEffect, useState } from 'react';
import MetricCard from '@/components/MetricCard';
import ServiceHealthGrid from '@/components/ServiceHealthGrid';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { mockServices } from '@/lib/mock-data';
import { api } from '@/lib/api';
import { Incident, IncidentStats } from '@/lib/types';
import { format } from 'date-fns';
import Link from 'next/link';

export default function DashboardPage() {
  const [incidents, setIncidents] = useState<Incident[]>([]);
  const [stats, setStats] = useState<IncidentStats | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    Promise.all([api.incidents({ limit: 5 }), api.incidentStats()])
      .then(([incidentsRes, statsRes]) => {
        if (!cancelled) {
          setIncidents(incidentsRes.incidents);
          setStats(statsRes);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err?.message || 'Failed to load dashboard data');
          setLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const mttrMinutes = stats ? `${Math.round(stats.mttr_hours * 60)} min` : '0 min';
  const activeIncidents = stats ? stats.by_status.triggered + stats.by_status.acknowledged : 0;
  const incidentsWeek = stats?.incidents_week ?? 0;
  const resolutionRate = stats && stats.total > 0 ? Math.round((stats.by_status.resolved / stats.total) * 100) : 0;

  return (
    <div className="p-6 md:p-8 space-y-8">
      <h1 className="font-serif text-3xl">Dashboard</h1>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading ? (
          [...Array(4)].map((_, i) => (
            <div key={i} className="bg-white rounded-xl border border-cream-dark shadow-sm p-5 animate-pulse">
              <div className="h-3 w-24 bg-gray-200 rounded" />
              <div className="h-8 w-20 bg-gray-200 rounded mt-2" />
              <div className="h-3 w-28 bg-gray-200 rounded mt-3" />
            </div>
          ))
        ) : (
          <>
            <MetricCard label="MTTR" value={mttrMinutes} />
            <MetricCard label="Active Incidents" value={String(activeIncidents)} />
            <MetricCard label="Incidents (7d)" value={String(incidentsWeek)} />
            <MetricCard label="Resolution Rate" value={`${resolutionRate}%`} />
          </>
        )}
      </div>

      {/* Service Health */}
      <section>
        <h2 className="font-serif text-xl mb-4">Service Health</h2>
        {/* TODO: Replace mock services once a real services API is available. */}
        <ServiceHealthGrid services={mockServices} />
      </section>

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
                {loading ? (
                  [...Array(5)].map((_, i) => (
                    <tr key={i} className="border-b border-cream-dark last:border-0">
                      <td className="px-4 py-3"><div className="h-4 w-28 bg-gray-200 rounded animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-4 w-24 bg-gray-200 rounded animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-5 w-16 bg-gray-200 rounded-full animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-5 w-20 bg-gray-200 rounded-full animate-pulse" /></td>
                      <td className="px-4 py-3"><div className="h-4 w-24 bg-gray-200 rounded animate-pulse" /></td>
                    </tr>
                  ))
                ) : error ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-red-500">
                      <p className="font-medium">Failed to load dashboard data</p>
                      <p className="text-sm text-gray-400 mt-1">{error}</p>
                    </td>
                  </tr>
                ) : incidents.length === 0 ? (
                  <tr>
                    <td colSpan={5} className="px-4 py-8 text-center text-gray-400">No incidents found.</td>
                  </tr>
                ) : incidents.map((inc) => (
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
              </tbody>
            </table>
          </div>
        </div>
      </section>
    </div>
  );
}
