'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useAnalyticsSummary, useTeamPerformance, useServiceHealth } from '@/hooks/use-analytics';
import { cn, formatDuration } from '@/lib/utils';
import {
  ArrowDown,
  ArrowUp,
  BarChart3,
  Clock,
  Download,
  Flame,
  Server,
  TrendingDown,
  TrendingUp,
  Users,
} from 'lucide-react';
import {
  AreaChart,
  Area,
  BarChart,
  Bar,
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts';

const periodOptions = ['day', 'week', 'month', 'quarter'] as const;

// Mock data
const mockTrendData = [
  { date: '2026-02-01', incidents: 24, mttr: 2.1 },
  { date: '2026-02-02', incidents: 18, mttr: 1.8 },
  { date: '2026-02-03', incidents: 31, mttr: 2.5 },
  { date: '2026-02-04', incidents: 15, mttr: 1.5 },
  { date: '2026-02-05', incidents: 22, mttr: 2.0 },
  { date: '2026-02-06', incidents: 28, mttr: 2.3 },
  { date: '2026-02-07', incidents: 12, mttr: 1.2 },
];

const mockSeverityData = [
  { name: 'Critical', value: 8, color: '#dc2626' },
  { name: 'High', value: 22, color: '#ea580c' },
  { name: 'Medium', value: 45, color: '#ca8a04' },
  { name: 'Low', value: 67, color: '#2563eb' },
  { name: 'Info', value: 23, color: '#6b7280' },
];

const mockSourceData = [
  { source: 'PagerDuty', count: 85 },
  { source: 'Datadog', count: 42 },
  { source: 'Opsgenie', count: 23 },
  { source: 'Manual', count: 15 },
];

const mockTeamData = [
  { team: 'Platform', incidents: 45, mttr: 1.8, mtta: 3.2 },
  { team: 'Backend', incidents: 38, mttr: 2.1, mtta: 4.5 },
  { team: 'Frontend', incidents: 22, mttr: 1.2, mtta: 2.8 },
  { team: 'Data', incidents: 28, mttr: 3.5, mtta: 5.1 },
  { team: 'DevOps', incidents: 32, mttr: 1.5, mtta: 2.1 },
];

const mockHeatmapData = Array.from({ length: 7 * 24 }, (_, i) => ({
  day: Math.floor(i / 24),
  hour: i % 24,
  value: Math.floor(Math.random() * 10),
}));

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<'day' | 'week' | 'month' | 'quarter'>('week');
  const { data: summary, isLoading } = useAnalyticsSummary(period);

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Analytics</h1>
          <p className="text-muted-foreground">
            Track performance metrics and incident trends
          </p>
        </div>
        <div className="flex items-center gap-4">
          <div className="flex items-center gap-1 rounded-lg border p-1">
            {periodOptions.map((p) => (
              <Button
                key={p}
                variant={period === p ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setPeriod(p)}
                className="capitalize"
              >
                {p}
              </Button>
            ))}
          </div>
          <Button variant="outline">
            <Download className="mr-2 h-4 w-4" />
            Export
          </Button>
        </div>
      </div>

      {/* Top Stats */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <MetricCard
          title="Total Incidents"
          value={summary?.incidents?.total_incidents ?? 165}
          change={summary?.incidents?.change_from_previous?.incidents ?? -12}
          icon={<Flame className="h-5 w-5" />}
          loading={isLoading}
        />
        <MetricCard
          title="MTTR"
          value={`${summary?.incidents?.mttr_hours?.toFixed(1) ?? 2.1}h`}
          change={summary?.incidents?.change_from_previous?.mttr ?? -18}
          icon={<Clock className="h-5 w-5" />}
          loading={isLoading}
          inverse
        />
        <MetricCard
          title="MTTA"
          value={`${summary?.incidents?.mtta_minutes?.toFixed(0) ?? 4}m`}
          change={summary?.incidents?.change_from_previous?.mtta ?? -8}
          icon={<TrendingDown className="h-5 w-5" />}
          loading={isLoading}
          inverse
        />
        <MetricCard
          title="Resolution Rate"
          value={`${((summary?.incidents?.resolved_incidents ?? 145) / (summary?.incidents?.total_incidents ?? 165) * 100).toFixed(0)}%`}
          change={5}
          icon={<BarChart3 className="h-5 w-5" />}
          loading={isLoading}
        />
      </div>

      {/* Charts Row 1 */}
      <div className="grid gap-4 lg:grid-cols-7">
        {/* Trend Chart */}
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>Incident Trend</CardTitle>
            <CardDescription>Incidents over time with MTTR overlay</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={mockTrendData}>
                  <defs>
                    <linearGradient id="colorIncidents" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#3b82f6" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#3b82f6" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis
                    dataKey="date"
                    className="text-xs"
                    tickFormatter={(v) => new Date(v).toLocaleDateString('en-US', { weekday: 'short' })}
                  />
                  <YAxis className="text-xs" yAxisId="left" />
                  <YAxis className="text-xs" yAxisId="right" orientation="right" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Area
                    yAxisId="left"
                    type="monotone"
                    dataKey="incidents"
                    stroke="#3b82f6"
                    fillOpacity={1}
                    fill="url(#colorIncidents)"
                    name="Incidents"
                  />
                  <Line
                    yAxisId="right"
                    type="monotone"
                    dataKey="mttr"
                    stroke="#f59e0b"
                    strokeWidth={2}
                    dot={false}
                    name="MTTR (hours)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Severity Distribution */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Severity Distribution</CardTitle>
            <CardDescription>Incidents by severity level</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[350px]">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={mockSeverityData}
                    cx="50%"
                    cy="50%"
                    innerRadius={60}
                    outerRadius={100}
                    paddingAngle={5}
                    dataKey="value"
                  >
                    {mockSeverityData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Charts Row 2 */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* By Source */}
        <Card>
          <CardHeader>
            <CardTitle>Incidents by Source</CardTitle>
            <CardDescription>Alert sources breakdown</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={mockSourceData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" className="text-xs" />
                  <YAxis dataKey="source" type="category" className="text-xs" width={80} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="count" fill="#3b82f6" radius={[0, 4, 4, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Team Performance */}
        <Card>
          <CardHeader>
            <CardTitle className="flex items-center gap-2">
              <Users className="h-5 w-5" />
              Team Performance
            </CardTitle>
            <CardDescription>MTTR by team</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={mockTeamData}>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="team" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="mttr" fill="#22c55e" name="MTTR (hours)" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Incident Heatmap */}
      <Card>
        <CardHeader>
          <CardTitle>Incident Heatmap</CardTitle>
          <CardDescription>When incidents occur throughout the week</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="overflow-x-auto">
            <div className="min-w-[800px]">
              <div className="flex gap-1">
                <div className="w-16 flex-shrink-0" />
                {Array.from({ length: 24 }, (_, i) => (
                  <div key={i} className="flex-1 text-center text-xs text-muted-foreground">
                    {i === 0 ? '12a' : i === 12 ? '12p' : i < 12 ? `${i}a` : `${i - 12}p`}
                  </div>
                ))}
              </div>
              {['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map((day, dayIndex) => (
                <div key={day} className="flex gap-1 mt-1">
                  <div className="w-16 flex-shrink-0 text-xs text-muted-foreground flex items-center">
                    {day}
                  </div>
                  {Array.from({ length: 24 }, (_, hourIndex) => {
                    const data = mockHeatmapData.find(
                      (d) => d.day === dayIndex && d.hour === hourIndex
                    );
                    const intensity = (data?.value ?? 0) / 10;
                    return (
                      <div
                        key={hourIndex}
                        className="flex-1 h-6 rounded"
                        style={{
                          backgroundColor: `rgba(239, 68, 68, ${intensity})`,
                        }}
                        title={`${day} ${hourIndex}:00 - ${data?.value ?? 0} incidents`}
                      />
                    );
                  })}
                </div>
              ))}
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Service Health */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Service Health
          </CardTitle>
          <CardDescription>Incident count and trend by service</CardDescription>
        </CardHeader>
        <CardContent>
          <div className="space-y-4">
            {[
              { name: 'payment-service', incidents: 23, critical: 5, trend: 'degrading' },
              { name: 'api-gateway', incidents: 18, critical: 2, trend: 'stable' },
              { name: 'user-service', incidents: 12, critical: 1, trend: 'improving' },
              { name: 'notification-service', incidents: 8, critical: 0, trend: 'improving' },
              { name: 'search-service', incidents: 15, critical: 3, trend: 'degrading' },
            ].map((service) => (
              <div
                key={service.name}
                className="flex items-center justify-between rounded-lg border p-4"
              >
                <div className="flex items-center gap-4">
                  <div
                    className={cn(
                      'h-3 w-3 rounded-full',
                      service.trend === 'improving' && 'bg-green-500',
                      service.trend === 'stable' && 'bg-yellow-500',
                      service.trend === 'degrading' && 'bg-red-500'
                    )}
                  />
                  <div>
                    <p className="font-medium">{service.name}</p>
                    <p className="text-sm text-muted-foreground">
                      {service.incidents} incidents • {service.critical} critical
                    </p>
                  </div>
                </div>
                <Badge
                  variant={
                    service.trend === 'improving'
                      ? 'success'
                      : service.trend === 'degrading'
                      ? 'destructive'
                      : 'secondary'
                  }
                >
                  {service.trend === 'improving' && <TrendingUp className="mr-1 h-3 w-3" />}
                  {service.trend === 'degrading' && <TrendingDown className="mr-1 h-3 w-3" />}
                  {service.trend}
                </Badge>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

interface MetricCardProps {
  title: string;
  value: string | number;
  change: number;
  icon: React.ReactNode;
  loading?: boolean;
  inverse?: boolean;
}

function MetricCard({ title, value, change, icon, loading, inverse }: MetricCardProps) {
  const isPositive = inverse ? change < 0 : change > 0;
  
  return (
    <Card>
      <CardContent className="p-6">
        {loading ? (
          <div className="space-y-2">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="h-8 w-16" />
            <Skeleton className="h-3 w-32" />
          </div>
        ) : (
          <>
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-muted-foreground">{title}</span>
              {icon}
            </div>
            <div className="mt-2">
              <span className="text-3xl font-bold">{value}</span>
            </div>
            <div className="mt-1 flex items-center gap-1 text-sm">
              {change !== 0 && (
                <span className={cn('flex items-center', isPositive ? 'text-green-500' : 'text-red-500')}>
                  {isPositive ? <ArrowUp className="h-3 w-3" /> : <ArrowDown className="h-3 w-3" />}
                  {Math.abs(change)}%
                </span>
              )}
              <span className="text-muted-foreground">vs previous period</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
