'use client';

import { useMemo, useState, type ComponentType } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Skeleton } from '@/components/ui/skeleton';
import { useInsights } from '@/hooks/use-analytics';
import { cn } from '@/lib/utils';
import type { InsightData } from '@/types/analytics';
import { Zap, AlertTriangle, TrendingUp, Lightbulb, Activity } from 'lucide-react';

type InsightTypeFilter = 'all' | InsightData['type'];
type SeverityFilter = 'all' | InsightData['severity'];

const typeFilters: Array<{ value: InsightTypeFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'pattern', label: 'Patterns' },
  { value: 'anomaly', label: 'Anomalies' },
  { value: 'recommendation', label: 'Recommendations' },
  { value: 'trend', label: 'Trends' },
];

const severityFilters: Array<{ value: SeverityFilter; label: string }> = [
  { value: 'all', label: 'All' },
  { value: 'critical', label: 'Critical' },
  { value: 'warning', label: 'Warning' },
  { value: 'info', label: 'Info' },
];

const typeStyleMap: Record<InsightData['type'], string> = {
  pattern:
    'bg-blue-500/15 text-blue-800 border-blue-300 dark:bg-blue-500/15 dark:text-blue-200 dark:border-blue-800',
  anomaly:
    'bg-rose-500/15 text-rose-800 border-rose-300 dark:bg-rose-500/15 dark:text-rose-200 dark:border-rose-800',
  recommendation:
    'bg-emerald-500/15 text-emerald-800 border-emerald-300 dark:bg-emerald-500/15 dark:text-emerald-200 dark:border-emerald-800',
  trend:
    'bg-violet-500/15 text-violet-800 border-violet-300 dark:bg-violet-500/15 dark:text-violet-200 dark:border-violet-800',
};

const typeIconMap: Record<InsightData['type'], ComponentType<{ className?: string }>> = {
  pattern: Activity,
  anomaly: AlertTriangle,
  recommendation: Lightbulb,
  trend: TrendingUp,
};

const severityBadgeMap: Record<InsightData['severity'], 'destructive' | 'warning' | 'secondary'> = {
  critical: 'destructive',
  warning: 'warning',
  info: 'secondary',
};

const relativeTimeFormatter = new Intl.RelativeTimeFormat('en', { numeric: 'auto' });

function formatRelativeTime(dateValue: string): string {
  const timestamp = new Date(dateValue).getTime();
  if (Number.isNaN(timestamp)) {
    return 'Unknown time';
  }

  const elapsed = timestamp - Date.now();
  const minute = 60 * 1000;
  const hour = 60 * minute;
  const day = 24 * hour;
  const week = 7 * day;
  const month = 30 * day;
  const year = 365 * day;

  if (Math.abs(elapsed) < minute) {
    return relativeTimeFormatter.format(Math.round(elapsed / 1000), 'second');
  }
  if (Math.abs(elapsed) < hour) {
    return relativeTimeFormatter.format(Math.round(elapsed / minute), 'minute');
  }
  if (Math.abs(elapsed) < day) {
    return relativeTimeFormatter.format(Math.round(elapsed / hour), 'hour');
  }
  if (Math.abs(elapsed) < week) {
    return relativeTimeFormatter.format(Math.round(elapsed / day), 'day');
  }
  if (Math.abs(elapsed) < month) {
    return relativeTimeFormatter.format(Math.round(elapsed / week), 'week');
  }
  if (Math.abs(elapsed) < year) {
    return relativeTimeFormatter.format(Math.round(elapsed / month), 'month');
  }
  return relativeTimeFormatter.format(Math.round(elapsed / year), 'year');
}

function formatConfidence(confidence?: number): string | null {
  if (typeof confidence !== 'number' || Number.isNaN(confidence)) {
    return null;
  }

  const normalized = confidence <= 1 ? confidence * 100 : confidence;
  return `${Math.round(Math.max(0, Math.min(normalized, 100)))}%`;
}

function InsightSkeletonCard() {
  return (
    <Card>
      <CardHeader className="space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <Skeleton className="h-5 w-24 rounded-full" />
            <Skeleton className="h-5 w-20 rounded-full" />
          </div>
          <Skeleton className="h-4 w-20" />
        </div>
        <Skeleton className="h-5 w-3/4" />
        <Skeleton className="h-4 w-full" />
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex gap-2">
          <Skeleton className="h-5 w-24 rounded-full" />
          <Skeleton className="h-5 w-24 rounded-full" />
        </div>
        <Skeleton className="h-4 w-1/2" />
        <Skeleton className="h-4 w-2/3" />
      </CardContent>
    </Card>
  );
}

function EmptyState({ hasInsights }: { hasInsights: boolean }) {
  return (
    <Card>
      <CardContent className="py-12 text-center">
        <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-muted">
          <Zap className="h-6 w-6 text-muted-foreground" />
        </div>
        <h3 className="text-lg font-semibold">
          {hasInsights ? 'No matching insights' : 'No insights available yet'}
        </h3>
        <p className="mt-2 text-sm text-muted-foreground">
          {hasInsights
            ? 'Try adjusting the type or severity filters to widen your results.'
            : 'AI-generated insights will appear here as incident patterns and anomalies are detected.'}
        </p>
      </CardContent>
    </Card>
  );
}

export default function InsightsPage() {
  const [typeFilter, setTypeFilter] = useState<InsightTypeFilter>('all');
  const [severityFilter, setSeverityFilter] = useState<SeverityFilter>('all');
  const { data, isLoading } = useInsights();

  const insights = useMemo(() => data ?? [], [data]);

  const filteredInsights = useMemo(() => {
    return insights.filter((insight) => {
      const matchesType = typeFilter === 'all' || insight.type === typeFilter;
      const matchesSeverity = severityFilter === 'all' || insight.severity === severityFilter;
      return matchesType && matchesSeverity;
    });
  }, [insights, severityFilter, typeFilter]);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-4 md:flex-row md:items-center md:justify-between">
        <div>
          <h1 className="text-3xl font-bold">AI Insights</h1>
          <p className="text-muted-foreground">
            AI-detected patterns, anomalies, and recommendations
          </p>
        </div>
        <Badge variant="outline" className="w-fit px-3 py-1 text-sm">
          {filteredInsights.length} of {insights.length} shown
        </Badge>
      </div>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-lg">
            <Zap className="h-5 w-5 text-yellow-500" />
            Filter Insights
          </CardTitle>
          <CardDescription>Focus on the insight categories and severity levels you care about.</CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {typeFilters.map((filter) => (
              <Button
                key={filter.value}
                variant={typeFilter === filter.value ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setTypeFilter(filter.value)}
              >
                {filter.label}
              </Button>
            ))}
          </div>
          <div className="flex flex-wrap gap-2">
            {severityFilters.map((filter) => (
              <Button
                key={filter.value}
                variant={severityFilter === filter.value ? 'secondary' : 'ghost'}
                size="sm"
                onClick={() => setSeverityFilter(filter.value)}
              >
                {filter.label}
              </Button>
            ))}
          </div>
        </CardContent>
      </Card>

      {isLoading ? (
        <div className="grid gap-4 md:grid-cols-2">
          {[...Array(4)].map((_, index) => (
            <InsightSkeletonCard key={index} />
          ))}
        </div>
      ) : filteredInsights.length === 0 ? (
        <EmptyState hasInsights={insights.length > 0} />
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {filteredInsights.map((insight) => {
            const InsightIcon = typeIconMap[insight.type];
            const confidence = formatConfidence(insight.confidence);

            return (
              <Card key={insight.id} className="transition-colors hover:bg-accent/30">
                <CardHeader className="space-y-3">
                  <div className="flex flex-wrap items-center justify-between gap-2">
                    <div className="flex items-center gap-2">
                      <Badge className={cn('gap-1 border', typeStyleMap[insight.type])}>
                        <InsightIcon className="h-3.5 w-3.5" />
                        <span className="capitalize">{insight.type}</span>
                      </Badge>
                      <Badge variant={severityBadgeMap[insight.severity]} className="capitalize">
                        {insight.severity}
                      </Badge>
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {formatRelativeTime(insight.created_at)}
                    </span>
                  </div>
                  <CardTitle className="text-base font-bold leading-snug">{insight.title}</CardTitle>
                  <CardDescription className="text-sm leading-relaxed">
                    {insight.description}
                  </CardDescription>
                </CardHeader>

                <CardContent className="space-y-4">
                  {insight.affected_services && insight.affected_services.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Affected Services
                      </p>
                      <div className="flex flex-wrap gap-2">
                        {insight.affected_services.map((service) => (
                          <Badge key={`${insight.id}-${service}`} variant="service" className="text-xs">
                            {service}
                          </Badge>
                        ))}
                      </div>
                    </div>
                  )}

                  {insight.recommended_actions && insight.recommended_actions.length > 0 && (
                    <div className="space-y-2">
                      <p className="text-xs font-medium uppercase tracking-wide text-muted-foreground">
                        Recommended Actions
                      </p>
                      <ul className="list-disc space-y-1 pl-5 text-sm text-muted-foreground">
                        {insight.recommended_actions.map((action, index) => (
                          <li key={`${insight.id}-action-${index}`}>{action}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {confidence && (
                    <div className="flex items-center gap-2 text-sm">
                      <Activity className="h-4 w-4 text-muted-foreground" />
                      <span className="text-muted-foreground">Confidence:</span>
                      <span className="font-semibold">{confidence}</span>
                    </div>
                  )}
                </CardContent>
              </Card>
            );
          })}
        </div>
      )}
    </div>
  );
}
