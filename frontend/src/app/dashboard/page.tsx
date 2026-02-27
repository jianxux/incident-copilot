'use client';
import MetricCard from '@/components/MetricCard';
import ServiceHealthGrid from '@/components/ServiceHealthGrid';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import { mockIncidents, mockServices } from '@/lib/mock-data';
import { format } from 'date-fns';
import Link from 'next/link';

export default function DashboardPage() {
  return (
    <div className="p-6 md:p-8 space-y-8">
      <h1 className="font-serif text-3xl">Dashboard</h1>

      {/* Metric Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <MetricCard label="MTTR" value="18 min" trend="down" trendLabel="38% improvement" trendPositive />
        <MetricCard label="Active Incidents" value="2" trend="up" trendLabel="+1 from yesterday" trendPositive={false} />
        <MetricCard label="Incidents (7d)" value="5" trend="down" trendLabel="-3 from last week" trendPositive />
        <MetricCard label="Resolution Rate" value="92%" trend="up" trendLabel="+5% this month" trendPositive />
      </div>

      {/* Service Health */}
      <section>
        <h2 className="font-serif text-xl mb-4">Service Health</h2>
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
                {mockIncidents.slice(0, 5).map((inc) => (
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
