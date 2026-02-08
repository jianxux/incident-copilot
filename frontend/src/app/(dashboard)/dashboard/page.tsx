'use client';

import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useIncidents, useIncidentStats } from '@/hooks/use-incidents';
import { useInsights } from '@/hooks/use-analytics';
import { formatDate, formatDuration } from '@/lib/utils';
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
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
} from 'recharts';

// Mock data for demo
const mockTrendData = [
  { date: 'Mon', incidents: 12, resolved: 10 },
  { date: 'Tue', incidents: 8, resolved: 8 },
  { date: 'Wed', incidents: 15, resolved: 12 },
  { date: 'Thu', incidents: 6, resolved: 6 },
  { date: 'Fri', incidents: 10, resolved: 9 },
  { date: 'Sat', incidents: 4, resolved: 4 },
  { date: 'Sun', incidents: 3, resolved: 3 },
];

const mockSeverityData = [
  { name: 'Critical', value: 3, color: '#dc2626' },
  { name: 'High', value: 8, color: '#ea580c' },
  { name: 'Medium', value: 15, color: '#ca8a04' },
  { name: 'Low', value: 22, color: '#2563eb' },
];

export default function DashboardPage() {
  const { data: statsData, isLoading: statsLoading } = useIncidentStats();
  const { data: incidentsData, isLoading: incidentsLoading } = useIncidents(
    { status: ['triggered', 'acknowledged'] },
    1,
    5
  );
  const { data: insights } = useInsights();

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
                <AreaChart data={mockTrendData}>
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
                <BarChart data={mockSeverityData} layout="vertical">
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
                    {mockSeverityData.map((entry, index) => (
                      <rect key={`bar-${index}`} fill={entry.color} />
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
            {incidentsLoading ? (
              <div className="space-y-4">
                {[...Array(3)].map((_, i) => (
                  <Skeleton key={i} className="h-16" />
                ))}
              </div>
            ) : (
              <div className="space-y-4">
                {incidentsData?.incidents?.slice(0, 5).map((incident) => (
                  <Link
                    key={incident.id}
                    href={`/incidents/${incident.id}`}
                    className="flex items-center justify-between rounded-lg border p-4 transition-colors hover:bg-accent"
                  >
                    <div className="space-y-1">
                      <div className="flex items-center gap-2">
                        <Badge variant={incident.severity as any}>
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
                )) || (
                  <p className="text-center text-muted-foreground py-8">
                    No active incidents 🎉
                  </p>
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
}

function StatsCard({ title, value, description, icon, trend, loading }: StatsCardProps) {
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
                    trend > 0 ? 'text-green-500' : 'text-red-500'
                  }`}
                >
                  {trend > 0 ? (
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
