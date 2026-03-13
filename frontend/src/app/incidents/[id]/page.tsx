'use client';
import { use, useState, useEffect } from 'react';
import Link from 'next/link';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import ContextCard from '@/components/ContextCard';
import VerdictDisplay from '@/components/VerdictDisplay';
import IncidentTimeline from '@/components/IncidentTimeline';
import { api } from '@/lib/api';
import { Incident, TimelineEvent, IncidentContext } from '@/lib/types';

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const [incident, setIncident] = useState<Incident | null>(null);
  const [timeline, setTimeline] = useState<TimelineEvent[]>([]);
  const [context, setContext] = useState<IncidentContext | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;

    Promise.all([
      api.incident(id),
      api.incidentTimeline(id).catch(() => []),
      api.incidentContext(id).catch(() => null),
    ])
      .then(([inc, tl, ctx]) => {
        if (!cancelled) {
          setIncident(inc);
          setTimeline(tl as TimelineEvent[]);
          setContext(ctx as IncidentContext | null);
          setLoading(false);
        }
      })
      .catch((err) => {
        if (!cancelled) {
          setError(err.message || 'Failed to load incident');
          setLoading(false);
        }
      });

    return () => { cancelled = true; };
  }, [id]);

  if (loading) {
    return (
      <div className="p-6 md:p-8 space-y-6">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-gray-200 rounded w-32" />
          <div className="h-8 bg-gray-200 rounded w-96" />
          <div className="h-4 bg-gray-200 rounded w-64" />
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mt-6">
            <div className="lg:col-span-2 space-y-4">
              <div className="h-48 bg-gray-200 rounded" />
              <div className="h-64 bg-gray-200 rounded" />
            </div>
            <div className="h-48 bg-gray-200 rounded" />
          </div>
        </div>
      </div>
    );
  }

  if (error || !incident) {
    return (
      <div className="p-6 md:p-8 space-y-6">
        <Link href="/incidents" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-coral transition-colors">
          <ArrowLeft size={16} /> Back to Incidents
        </Link>
        <div className="text-center py-12 text-red-500">
          <p className="font-medium">Failed to load incident</p>
          <p className="text-sm text-gray-400 mt-1">{error}</p>
        </div>
      </div>
    );
  }

  // Build verdict from context/incident data if available
  const verdict = incident.verdict_summary ? {
    summary: incident.verdict_summary,
    root_cause_hypothesis: '',
    confidence: 0,
    key_findings: [] as string[],
    recommended_actions: [] as string[],
    rollback_recommended: false,
  } : undefined;

  // Map timeline events for the IncidentTimeline component
  const timelineEvents = timeline.map((evt) => ({
    id: evt.id,
    timestamp: evt.timestamp,
    type: evt.type as 'alert' | 'investigation' | 'action' | 'resolution' | 'deployment',
    title: evt.title || evt.type.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase()),
    description: evt.description,
  }));

  const timelineEmptyMessage = (() => {
    switch (context?.github_status) {
      case 'no_credentials':
        return 'No timeline events yet. Connect GitHub to enrich this incident with commits, pull requests, and deployments.';
      case 'no_repo_mapping':
        return 'No timeline events yet. GitHub is connected, but this service is not mapped to a repository.';
      case 'connected':
      case 'enriched':
        return 'No timeline events yet. GitHub is connected, but no related commits, pull requests, or deployments were found.';
      default:
        return 'No timeline events yet';
    }
  })();

  return (
    <div className="p-6 md:p-8 space-y-6">
      <Link href="/incidents" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-coral transition-colors">
        <ArrowLeft size={16} /> Back to Incidents
      </Link>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="font-serif text-2xl md:text-3xl">{incident.id.slice(0, 8)}</h1>
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
          </div>
          <p className="text-gray-600">{incident.title}</p>
          {incident.description && <p className="text-gray-500 text-sm mt-1">{incident.description}</p>}
        </div>
        <div className="text-sm text-gray-500 space-y-1 shrink-0">
          <p>Service: <strong className="text-gray-700">{incident.service}</strong></p>
          <p>Source: {incident.source} {incident.source_url && <a href={incident.source_url} className="text-coral"><ExternalLink size={12} className="inline" /></a>}</p>
          <p>Triggered: {format(new Date(incident.triggered_at), 'MMM d, yyyy HH:mm:ss')}</p>
          {incident.assignee && <p>Assignee: <strong className="text-gray-700">{incident.assignee}</strong></p>}
          {incident.duration_seconds != null && (
            <p>Duration: {incident.duration_seconds < 3600
              ? `${Math.round(incident.duration_seconds / 60)}m`
              : `${(incident.duration_seconds / 3600).toFixed(1)}h`}
            </p>
          )}
        </div>
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          {verdict && <ContextCard verdict={verdict} />}
          {timelineEvents.length > 0 ? (
            <IncidentTimeline events={timelineEvents} />
          ) : (
            <div className="bg-white rounded-xl border border-cream-dark p-6 text-center text-gray-400">
              {timelineEmptyMessage}
            </div>
          )}
        </div>
        <div className="space-y-6">
          {verdict ? (
            <VerdictDisplay verdict={verdict} />
          ) : (
            <div className="bg-white rounded-xl border border-cream-dark p-6 text-center text-gray-400">
              No AI verdict available
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
