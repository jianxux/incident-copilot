'use client';
import { mockAnalytics } from '@/lib/mock-data';
import { LineChart, Line, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, PieChart, Pie, Cell, BarChart, Bar, PieLabelRenderProps } from 'recharts';

const COLORS = ['#dc2626', '#ea580c', '#eab308', '#22c55e'];

export default function AnalyticsPage() {
  const { mttr_trend, incidents_by_severity, resolution_times } = mockAnalytics;

  return (
    <div className="p-6 md:p-8 space-y-8">
      <h1 className="font-serif text-3xl">Analytics</h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {/* MTTR Trend */}
        <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6">
          <h3 className="font-serif text-lg mb-4">MTTR Trend (7 days)</h3>
          <ResponsiveContainer width="100%" height={250}>
            <LineChart data={mttr_trend}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ebe0" />
              <XAxis dataKey="date" tick={{ fontSize: 12 }} tickFormatter={(v) => v.slice(5)} />
              <YAxis tick={{ fontSize: 12 }} unit=" min" />
              <Tooltip />
              <Line type="monotone" dataKey="mttr_minutes" stroke="#e05a3a" strokeWidth={2} dot={{ fill: '#e05a3a' }} />
            </LineChart>
          </ResponsiveContainer>
        </div>

        {/* Severity Distribution */}
        <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6">
          <h3 className="font-serif text-lg mb-4">Incidents by Severity</h3>
          <ResponsiveContainer width="100%" height={250}>
            <PieChart>
              <Pie data={incidents_by_severity} dataKey="count" nameKey="severity" cx="50%" cy="50%" outerRadius={90} label={(props: PieLabelRenderProps) => `${props.name}: ${props.value}`}>
                {incidents_by_severity.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Pie>
              <Tooltip />
            </PieChart>
          </ResponsiveContainer>
        </div>

        {/* Resolution Times by Service */}
        <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6 lg:col-span-2">
          <h3 className="font-serif text-lg mb-4">Avg Resolution Time by Service</h3>
          <ResponsiveContainer width="100%" height={250}>
            <BarChart data={resolution_times}>
              <CartesianGrid strokeDasharray="3 3" stroke="#f0ebe0" />
              <XAxis dataKey="service" tick={{ fontSize: 11 }} />
              <YAxis tick={{ fontSize: 12 }} unit=" min" />
              <Tooltip />
              <Bar dataKey="avg_minutes" fill="#e05a3a" radius={[4, 4, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  );
}
