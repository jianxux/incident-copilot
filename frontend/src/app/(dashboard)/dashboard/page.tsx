'use client';

import { useMemo } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useIncidents, useIncidentStats } from '@/hooks/use-incidents';
import { useInsights } from '@/hooks/use-analytics';
import { formatDate } from '@/lib/utils';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  Eye,
  Flame,
  TrendingDown,
  TrendingUp,
  Zap,
} from 'lucide-react';
import Link from 'next/link';
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  Cell,
} from 'recharts';

const severityVariant: Record<string, BadgeProps['variant']> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
  info: 'info',
};

const severityChartConfig = {
  critical: { label: 'Critical', color: '#dc2626' },
  high: { label: 'High', color: '#ea580c' },
  medium: { label: 'Medium', color: '#ca8a04' },
  low: { label: 'Low', color: '#2563eb' },
  info: { label: 'Info', color: '#6b7280' },
} as const;

export default function DashboardPage() {
  const { data: statsData, isLoading: statsLoading } = useIncidentStats();
  const { data: activeIncidentsData, isLoading: activeIncidentsLoading } = useIncidents(
    { status: ['triggered', 'acknowledged'] },
    1,
    5
  );
  const { data: incidentsData } = useIncidents(undefined, 1, 100);
  const { data: insights } = useInsights();

  const trendData = useMemo(() => {
    const statsWithBreakdown = statsData as
      | {
          daily_breakdown?: Array<{ date: string; incidents: number; resolved: number }>;
          weekly_breakdown?: Array<{ date: string; incidents: number; resolved: number }>;
        }
      | undefined;

    if (statsWithBreakdown?.daily_breakdown?.length) {
      return statsWithBreakdown.daily_breakdown;
    }

    if (statsWithBreakdown?.weekly_breakdown?.length) {
      return statsWithBreakdown.weekly_breakdown;
    }

    const allIncidents = incidentsData?.incidents ?? [];
    if (!allIncidents.length) {
      return [];
    }

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    const buckets = Array.from({ length: 7 }, (_, index) => {
      const date = new Date(today);
      date.setDate(today.getDate() - (6 - index));
      const key = date.toISOString().slice(0, 10);

      return {
        key,
        date: date.toLocaleDateString('en-US', { weekday: 'short' }),
        incidents: 0,
        resolved: 0,
      };
    });

    const bucketMap = new Map(buckets.map((entry) => [entry.key, entry]));

    allIncidents.forEach((incident) => {
      const createdKey = new Date(incident.created_at).toISOString().slice(0, 10);
      const createdBucket = bucketMap.get(createdKey);
      if (createdBucket) {
        createdBucket.incidents += 1;
      }

      if (incident.resolved_at) {
        const resolvedKey = new Date(incident.resolved_at).toISOString().slice(0, 10);
        const resolvedBucket = bucketMap.get(resolvedKey);
        if (resolvedBucket) {
          resolvedBucket.resolved += 1;
        }
      }
    });

    return buckets.map(({ date, incidents, resolved }) => ({ date, incidents, resolved }));
  }, [incidentsData?.incidents, statsData]);

  const severityData = useMemo(() => {
    if (statsData?.by_severity) {
      return (Object.keys(severityChartConfig) as Array<keyof typeof severityChartConfig>).map(
        (severity) => ({
          name: severityChartConfig[severity].label,
          value: statsData.by_severity[severity] ?? 0,
          color: severityChartConfig[severity].color,
        })
      );
    }

    if (statsData?.by_status) {
      return [
        { name: 'Triggered', value: statsData.by_status.triggered ?? 0, color: '#dc2626' },
        { name: 'Acknowledged', value: statsData.by_status.acknowledged ?? 0, color: '#f59e0b' },
        { name: 'Resolved', value: statsData.by_status.resolved ?? 0, color: '#16a34a' },
        { name: 'Processing', value: statsData.by_status.processing ?? 0, color: '#2563eb' },
      ];
    }

    return [];
  }, [statsData]);

  const activeIncidents = activeIncidentsData?.incidents?.slice(0, 5) ?? [];

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Dashboard</h1>
          <p className="text-muted-foreground">
            Welcome back! Here's what's happening with your incidents.
          </p>
        </div>
        <Button asChild>
          <Link href="/incidents/new">
            <AlertTriangle className="mr-2 h-4 w-4" />
            Create Incident
          </Link>
        </Button>
      </div>

      {/* Stats Grid */}
      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        <StatsCard
          title="Active Incidents"
          value={statsData?.by_status?.triggered ?? 0}
          description="Triggered alerts"
          icon={<Flame className="h-5 w-5 text-red-500" />}
          trend={-12}
          loading={statsLoading}
          invertTrend
        />
        <StatsCard
          title="Acknowledged"
          value={statsData?.by_status?.acknowledged ?? 0}
          description="Being worked on"
          icon={<Eye className="h-5 w-5 text-yellow-500" />}
          trend={5}
          loading={statsLoading}
        />
        <StatsCard
          title="MTTR"
          value={`${statsData?.mttr_hours?.toFixed(1) ?? '0'}h`}
          description="Mean time to resolve"
          icon={<Clock className="h-5 w-5 text-blue-500" />}
          trend={-8}
          loading={statsLoading}
          invertTrend
        />
        <StatsCard
          title="Resolved Today"
          value={statsData?.incidents_today ?? 0}
          description="Incidents closed"
          icon={<CheckCircle2 className="h-5 w-5 text-green-500" />}
          trend={15}
          loading={statsLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid gap-4 lg:grid-cols-7">
        {/* Incident Trend */}
        <Card className="lg:col-span-4">
          <CardHeader>
            <CardTitle>Incident Trend</CardTitle>
            <CardDescription>Incidents created vs resolved this week</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={trendData}>
                  <defs>
                    <linearGradient id="colorIncidents" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#ef4444" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#ef4444" stopOpacity={0} />
                    </linearGradient>
                    <linearGradient id="colorResolved" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="#22c55e" stopOpacity={0.3} />
                      <stop offset="95%" stopColor="#22c55e" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis dataKey="date" className="text-xs" />
                  <YAxis className="text-xs" />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="incidents"
                    stroke="#ef4444"
                    fillOpacity={1}
                    fill="url(#colorIncidents)"
                  />
                  <Area
                    type="monotone"
                    dataKey="resolved"
                    stroke="#22c55e"
                    fillOpacity={1}
                    fill="url(#colorResolved)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>

        {/* Severity Breakdown */}
        <Card className="lg:col-span-3">
          <CardHeader>
            <CardTitle>By Severity</CardTitle>
            <CardDescription>Active incidents breakdown</CardDescription>
          </CardHeader>
          <CardContent>
            <div className="h-[300px]">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={severityData} layout="vertical">
                  <CartesianGrid strokeDasharray="3 3" className="stroke-muted" />
                  <XAxis type="number" className="text-xs" />
                  <YAxis dataKey="name" type="category" className="text-xs" width={60} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: 'hsl(var(--card))',
                      border: '1px solid hsl(var(--border))',
                      borderRadius: '8px',
                    }}
                  />
                  <Bar dataKey="value" radius={[0, 4, 4, 0]}>
                    {severityData.map((entry, index) => (
                      <Cell key={`bar-${index}`} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Bottom Row */}
      <div className="grid gap-4 lg:grid-cols-2">
        {/* Active Incidents */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle>Active Incidents</CardTitle>
              <CardDescription>Incidents requiring attention</CardDescription>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href="/incidents">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            {activeIncidentsLoading ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {activeIncidents.length > 0 ? (
                  activeIncidents.map((incident) => (
                    <Link
                      key={incident.id}
                      href={`/incidents/${incident.id}`}
                      className="flex items-center justify-between rounded-lg border p-4 transition-colors hover:bg-accent"
                    >
                      <div className="space-y-1">
                        <div className="flex items-center gap-2">
                          <Badge variant={severityVariant[incident.severity] ?? 'secondary'}>
                            {incident.severity}
                          </Badge>
                          <span className="font-medium">{incident.title}</span>
                        </div>
                        <p className="text-sm text-muted-foreground">
                          {incident.service} • {formatDate(incident.created_at)}
                        </p>
                      </div>
                      <Badge
                        variant={
                          incident.status === 'triggered' ? 'destructive' : 'warning'
                        }
                      >
                        {incident.status}
                      </Badge>
                    </Link>
                  ))
                ) : (
                  <div className="flex flex-col items-center py-8">
                    <CheckCircle2 className="h-8 w-8 text-green-500 mb-2" />
                    <p className="font-medium">No active incidents</p>
                    <p className="text-sm text-muted-foreground">All clear — nothing needs attention right now.</p>
                  </div>
                )}
              </div>
            )}
          </CardContent>
        </Card>

        {/* AI Insights */}
        <Card>
          <CardHeader className="flex flex-row items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-yellow-500" />
                AI Insights
              </CardTitle>
              <CardDescription>Patterns and recommendations</CardDescription>
            </div>
            <Button variant="outline" size="sm" asChild>
              <Link href="/insights">View all</Link>
            </Button>
          </CardHeader>
          <CardContent>
            <div className="space-y-4">
              {insights?.slice(0, 3).map((insight) => (
                <div
                  key={insight.id}
                  className="rounded-lg border p-4 space-y-2"
                >
                  <div className="flex items-center gap-2">
                    <Badge variant={insight.severity === 'critical' ? 'destructive' : insight.severity === 'warning' ? 'warning' : 'secondary'}>
                      {insight.type}
                    </Badge>
                    <span className="text-xs text-muted-foreground">
                      {formatDate(insight.created_at)}
                    </span>
                  </div>
                  <p className="font-medium">{insight.title}</p>
                  <p className="text-sm text-muted-foreground">{insight.description}</p>
                </div>
              )) || (
                <>
                  <div className="rounded-lg border p-4 space-y-2">
                    <Badge variant="warning">pattern</Badge>
                    <p className="font-medium">Recurring API timeout pattern detected</p>
                    <p className="text-sm text-muted-foreground">
                      3 similar incidents in the last 24 hours affecting payment-service
                    </p>
                  </div>
                  <div className="rounded-lg border p-4 space-y-2">
                    <Badge variant="secondary">recommendation</Badge>
                    <p className="font-medium">Consider increasing connection pool size</p>
                    <p className="text-sm text-muted-foreground">
                      Database connection exhaustion has occurred 5 times this week
                    </p>
                  </div>
                </>
              )}
            </div>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}

interface StatsCardProps {
  title: string;
  value: string | number;
  description: string;
  icon: React.ReactNode;
  trend?: number;
  loading?: boolean;
  invertTrend?: boolean;
}

function StatsCard({ title, value, description, icon, trend, loading, invertTrend }: StatsCardProps) {
  const isPositiveTrend = (trend ?? 0) > 0;
  const trendIsGood = invertTrend ? !isPositiveTrend : isPositiveTrend;

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
            <div className="mt-1 flex items-center gap-2 text-sm">
              {trend !== undefined && (
                <span
                  className={`flex items-center ${
                    trendIsGood ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {isPositiveTrend ? (
                    <TrendingUp className="mr-1 h-3 w-3" />
                  ) : (
                    <TrendingDown className="mr-1 h-3 w-3" />
                  )}
                  {Math.abs(trend)}%
                </span>
              )}
              <span className="text-muted-foreground">{description}</span>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  );
}
