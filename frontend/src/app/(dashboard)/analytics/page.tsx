'use client';

import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useAnalyticsSummary, useHeatmap } from '@/hooks/use-analytics';
import { cn } from '@/lib/utils';
import type { HeatmapData } from '@/types/analytics';
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

export default function AnalyticsPage() {
  const [period, setPeriod] = useState<'day' | 'week' | 'month' | 'quarter'>('week');
  const { data: summary, isLoading } = useAnalyticsSummary(period);
  const { data: heatmap, isLoading: isHeatmapLoading } = useHeatmap();

  const trendData = summary?.trends ?? [];
  const severityData = summary
    ? [
        { name: 'Critical', value: summary.incidents.by_severity.critical, color: '#dc2626' },
        { name: 'High', value: summary.incidents.by_severity.high, color: '#ea580c' },
        { name: 'Medium', value: summary.incidents.by_severity.medium, color: '#ca8a04' },
        { name: 'Low', value: summary.incidents.by_severity.low, color: '#2563eb' },
        { name: 'Info', value: summary.incidents.by_severity.info, color: '#6b7280' },
      ]
    : [];
  const sourceData = Object.entries(summary?.incidents.by_source ?? {}).map(([source, count]) => ({
    source,
    count,
  }));
  const teamData = (summary?.team_performance ?? []).map((team) => ({
    team: team.team_name,
    incidents: team.incidents_handled,
    mttr: team.avg_resolution_time_hours,
    mtta: team.avg_response_time_minutes,
  }));
  const serviceHealth = summary?.service_health ?? [];
  const heatmapData: Array<{ day: number; hour: number; value: number }> = (
    Array.isArray(heatmap) ? (heatmap as HeatmapData[]) : []
  ).map((item: HeatmapData) => ({
    day: item.day_of_week,
    hour: item.hour_of_day,
    value: item.incident_count,
  }));

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
          value={summary?.incidents.total_incidents ?? 0}
          change={summary?.incidents.change_from_previous.incidents ?? 0}
          icon={<Flame className="h-5 w-5" />}
          loading={isLoading}
        />
        <MetricCard
          title="MTTR"
          value={`${(summary?.incidents.mttr_hours ?? 0).toFixed(1)}h`}
          change={summary?.incidents.change_from_previous.mttr ?? 0}
          icon={<Clock className="h-5 w-5" />}
          loading={isLoading}
          inverse
        />
        <MetricCard
          title="MTTA"
          value={`${(summary?.incidents.mtta_minutes ?? 0).toFixed(0)}m`}
          change={summary?.incidents.change_from_previous.mtta ?? 0}
          icon={<TrendingDown className="h-5 w-5" />}
          loading={isLoading}
          inverse
        />
        <MetricCard
          title="Resolution Rate"
          value={`${(((summary?.incidents.resolved_incidents ?? 0) / Math.max(summary?.incidents.total_incidents ?? 0, 1)) * 100).toFixed(0)}%`}
          change={0}
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
            {isLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : trendData.length === 0 ? (
              <EmptyChartState message="No trend data available for this period." />
            ) : (
              <div className="h-[350px]">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={trendData}>
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
                      tickFormatter={(v) =>
                        new Date(v).toLocaleDateString('en-US', { weekday: 'short' })
                      }
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
                      dataKey="mttr_hours"
                      stroke="#f59e0b"
                      strokeWidth={2}
                      dot={false}
                      name="MTTR (hours)"
                    />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            )}
          </CardContent>
        </Card>

        {/* Severity Distribution */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>Severity Distribution</CardTitle>
            <CardDescription>Incidents by severity level</CardDescription>
          </CardHeader>
          <CardContent>
            {isLoading ? (
              <Skeleton className="h-[350px] w-full" />
            ) : severityData.length === 0 ? (
              <EmptyChartState message="No severity data available for this period." />
            ) : (
              <div className="h-[350px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={severityData}
                      cx="50%"
                      cy="50%"
                      innerRadius={60}
                      outerRadius={100}
                      paddingAngle={5}
                      dataKey="value"
                    >
                      {severityData.map((entry, index) => (
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
            )}
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
            {isLoading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : sourceData.length === 0 ? (
              <EmptyChartState message="No source data available for this period." />
            ) : (
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={sourceData} layout="vertical">
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
            )}
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
            {isLoading ? (
              <Skeleton className="h-[300px] w-full" />
            ) : teamData.length === 0 ? (
              <EmptyChartState message="No team performance data available for this period." />
            ) : (
              <div className="h-[300px]">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={teamData}>
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
                    <Bar
                      dataKey="mttr"
                      fill="#22c55e"
                      name="MTTR (hours)"
                      radius={[4, 4, 0, 0]}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            )}
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
          {isHeatmapLoading ? (
            <Skeleton className="h-[240px] w-full" />
          ) : heatmapData.length === 0 ? (
            <EmptyChartState message="No heatmap data available for this period." />
          ) : (
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
                      const data = heatmapData.find(
                        (d) => d.day === dayIndex && d.hour === hourIndex
                      );
                      const intensity = Math.min((data?.value ?? 0) / 10, 1);
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
          )}
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
          {isLoading ? (
            <div className="space-y-4">
              {Array.from({ length: 4 }).map((_, idx) => (
                <Skeleton key={idx} className="h-20 w-full" />
              ))}
            </div>
          ) : serviceHealth.length === 0 ? (
            <EmptyChartState message="No service health data available for this period." />
          ) : (
            <div className="space-y-4">
              {serviceHealth.map((service) => (
                <div
                  key={service.service_id}
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
                      <p className="font-medium">{service.service_name}</p>
                      <p className="text-sm text-muted-foreground">
                        {service.incident_count} incidents • {service.critical_count} critical
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
          )}
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

function EmptyChartState({ message }: { message: string }) {
  return (
    <div className="flex h-[300px] items-center justify-center text-sm text-muted-foreground">
      {message}
    </div>
  );
}
