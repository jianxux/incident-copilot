'use client';

import { useState } from 'react';
import { useParams, useRouter } from 'next/navigation';
import Link from 'next/link';
import {
  useIncident,
  useIncidentContext,
  useIncidentTimeline,
  useSimilarIncidents,
  useAcknowledgeIncident,
  useResolveIncident,
  useAddNote,
} from '@/hooks/use-incidents';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge, type BadgeProps } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import { Separator } from '@/components/ui/separator';
import { formatDate, formatDuration, cn } from '@/lib/utils';
import {
  AlertTriangle,
  ArrowLeft,
  BookOpen,
  Brain,
  CheckCircle,
  ChevronRight,
  Clock,
  ExternalLink,
  Eye,
  GitBranch,
  GitCommit,
  MessageSquare,
  Phone,
  Play,
  Send,
  User,
  Users,
  Zap,
} from 'lucide-react';

const severityVariant: Record<string, BadgeProps['variant']> = {
  critical: 'critical',
  high: 'high',
  medium: 'medium',
  low: 'low',
  info: 'info',
};

export default function IncidentDetailPage() {
  const params = useParams();
  const router = useRouter();
  const id = params.id as string;
  
  const [note, setNote] = useState('');
  
  const { data: incident, isLoading } = useIncident(id);
  const { data: context } = useIncidentContext(id);
  const { data: timeline } = useIncidentTimeline(id);
  const { data: similar } = useSimilarIncidents(id);
  
  const acknowledgeIncident = useAcknowledgeIncident();
  const resolveIncident = useResolveIncident();
  const addNote = useAddNote();

  const handleAddNote = () => {
    if (note.trim()) {
      addNote.mutate({ id, note });
      setNote('');
    }
  };

  if (isLoading) {
    return (
      <div className="space-y-6">
        <Skeleton className="h-10 w-64" />
        <div className="grid gap-6 lg:grid-cols-3">
          <div className="lg:col-span-2 space-y-6">
            <Skeleton className="h-[200px]" />
            <Skeleton className="h-[300px]" />
          </div>
          <div className="space-y-6">
            <Skeleton className="h-[200px]" />
            <Skeleton className="h-[200px]" />
          </div>
        </div>
      </div>
    );
  }

  if (!incident) {
    return (
      <div className="flex flex-col items-center justify-center py-16">
        <AlertTriangle className="h-12 w-12 text-muted-foreground" />
        <h2 className="mt-4 text-xl font-semibold">Incident not found</h2>
        <Button variant="outline" className="mt-4" onClick={() => router.back()}>
          Go back
        </Button>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div className="space-y-1">
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Link href="/incidents" className="hover:text-foreground">
              Incidents
            </Link>
            <ChevronRight className="h-4 w-4" />
            <span>{incident.id.slice(0, 8)}</span>
          </div>
          <div className="flex items-center gap-3">
            <Badge variant={severityVariant[incident.severity] ?? 'secondary'} className="text-base px-3 py-1">
              {incident.severity}
            </Badge>
            <h1 className="text-2xl font-bold">{incident.title}</h1>
          </div>
        </div>
        
        <div className="flex items-center gap-2">
          {incident.status === 'triggered' && (
            <Button
              variant="outline"
              onClick={() => acknowledgeIncident.mutate(id)}
              disabled={acknowledgeIncident.isPending}
            >
              <Eye className="mr-2 h-4 w-4" />
              Acknowledge
            </Button>
          )}
          {incident.status !== 'resolved' && (
            <Button
              onClick={() => resolveIncident.mutate({ id })}
              disabled={resolveIncident.isPending}
            >
              <CheckCircle className="mr-2 h-4 w-4" />
              Resolve
            </Button>
          )}
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        {/* Main content */}
        <div className="lg:col-span-2 space-y-6">
          {/* Status & metrics */}
          <Card>
            <CardHeader>
              <CardTitle>Status</CardTitle>
            </CardHeader>
            <CardContent>
              <div className="grid gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-sm text-muted-foreground">Status</p>
                  <Badge
                    variant={
                      incident.status === 'triggered'
                        ? 'destructive'
                        : incident.status === 'acknowledged'
                        ? 'warning'
                        : 'success'
                    }
                    className="mt-1"
                  >
                    {incident.status}
                  </Badge>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">Created</p>
                  <p className="mt-1 font-medium">{formatDate(incident.created_at)}</p>
                </div>
                {incident.acknowledged_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Acknowledged</p>
                    <p className="mt-1 font-medium">{formatDate(incident.acknowledged_at)}</p>
                  </div>
                )}
                {incident.resolved_at && (
                  <div>
                    <p className="text-sm text-muted-foreground">Resolved</p>
                    <p className="mt-1 font-medium">{formatDate(incident.resolved_at)}</p>
                  </div>
                )}
              </div>
              
              {(incident.tta || incident.ttr) && (
                <>
                  <Separator className="my-4" />
                  <div className="grid gap-4 sm:grid-cols-3">
                    {incident.tta && (
                      <div>
                        <p className="text-sm text-muted-foreground">Time to Acknowledge</p>
                        <p className="mt-1 text-2xl font-bold">{formatDuration(incident.tta)}</p>
                      </div>
                    )}
                    {incident.ttr && (
                      <div>
                        <p className="text-sm text-muted-foreground">Time to Resolve</p>
                        <p className="mt-1 text-2xl font-bold">{formatDuration(incident.ttr)}</p>
                      </div>
                    )}
                  </div>
                </>
              )}
            </CardContent>
          </Card>

          {/* AI Summary */}
          {context?.ai_summary && (
            <Card className="border-l-4 border-l-yellow-500">
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Brain className="h-5 w-5 text-yellow-500" />
                  AI Analysis
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-4">
                <div>
                  <h4 className="font-semibold">Summary</h4>
                  <p className="mt-1 text-muted-foreground">{context.ai_summary.summary}</p>
                </div>
                {context.ai_summary.root_cause && (
                  <div>
                    <h4 className="font-semibold">Possible Root Cause</h4>
                    <p className="mt-1 text-muted-foreground">{context.ai_summary.root_cause}</p>
                  </div>
                )}
                {context.ai_summary.recommended_actions && (
                  <div>
                    <h4 className="font-semibold">Recommended Actions</h4>
                    <ul className="mt-1 list-disc list-inside text-muted-foreground">
                      {context.ai_summary.recommended_actions.map((action, i) => (
                        <li key={i}>{action}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </CardContent>
            </Card>
          )}

          {/* Recent Changes */}
          {context?.github_context && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <GitBranch className="h-5 w-5" />
                  Recent Changes
                </CardTitle>
                <CardDescription>Code and deployment activity</CardDescription>
              </CardHeader>
              <CardContent>
                {context.github_context.recent_commits?.length ? (
                  <div className="space-y-3">
                    {context.github_context.recent_commits.slice(0, 5).map((commit) => (
                      <a
                        key={commit.sha}
                        href={commit.url}
                        target="_blank"
                        rel="noopener noreferrer"
                        className="flex items-start gap-3 rounded-lg border p-3 transition-colors hover:bg-accent"
                      >
                        <GitCommit className="h-4 w-4 mt-1 text-muted-foreground" />
                        <div className="flex-1 min-w-0">
                          <p className="font-medium truncate">{commit.message}</p>
                          <div className="flex items-center gap-2 text-sm text-muted-foreground">
                            <span>{commit.author}</span>
                            <span>•</span>
                            <span>{formatDate(commit.timestamp)}</span>
                          </div>
                        </div>
                        <ExternalLink className="h-4 w-4 text-muted-foreground" />
                      </a>
                    ))}
                  </div>
                ) : (
                  <p className="text-center text-muted-foreground py-4">No recent commits found</p>
                )}
              </CardContent>
            </Card>
          )}

          {/* Timeline */}
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Clock className="h-5 w-5" />
                Timeline
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div className="relative pl-6 border-l-2 border-muted space-y-6">
                {timeline?.map((event) => (
                  <div key={event.id} className="relative">
                    <div className="absolute -left-[25px] h-4 w-4 rounded-full bg-background border-2 border-primary" />
                    <div>
                      <p className="font-medium">{event.description}</p>
                      <div className="flex items-center gap-2 text-sm text-muted-foreground">
                        {event.actor && <span>{event.actor}</span>}
                        <span>•</span>
                        <span>{formatDate(event.timestamp)}</span>
                      </div>
                    </div>
                  </div>
                )) || (
                  <>
                    <div className="relative">
                      <div className="absolute -left-[25px] h-4 w-4 rounded-full bg-background border-2 border-red-500" />
                      <p className="font-medium">Incident triggered</p>
                      <p className="text-sm text-muted-foreground">{formatDate(incident.created_at)}</p>
                    </div>
                    {incident.acknowledged_at && (
                      <div className="relative">
                        <div className="absolute -left-[25px] h-4 w-4 rounded-full bg-background border-2 border-yellow-500" />
                        <p className="font-medium">Incident acknowledged</p>
                        <p className="text-sm text-muted-foreground">{formatDate(incident.acknowledged_at)}</p>
                      </div>
                    )}
                    {incident.resolved_at && (
                      <div className="relative">
                        <div className="absolute -left-[25px] h-4 w-4 rounded-full bg-background border-2 border-green-500" />
                        <p className="font-medium">Incident resolved</p>
                        <p className="text-sm text-muted-foreground">{formatDate(incident.resolved_at)}</p>
                      </div>
                    )}
                  </>
                )}
              </div>
              
              {/* Add note */}
              <div className="mt-6 flex gap-2">
                <Input
                  placeholder="Add a note..."
                  value={note}
                  onChange={(e) => setNote(e.target.value)}
                  onKeyDown={(e) => e.key === 'Enter' && handleAddNote()}
                />
                <Button size="icon" onClick={handleAddNote} disabled={addNote.isPending}>
                  <Send className="h-4 w-4" />
                </Button>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* Sidebar */}
        <div className="space-y-6">
          {/* Details */}
          <Card>
            <CardHeader>
              <CardTitle>Details</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-sm text-muted-foreground">Service</p>
                <Badge variant="service">{incident.service}</Badge>
              </div>
              <div>
                <p className="text-sm text-muted-foreground">Source</p>
                <p className="font-medium">{incident.source}</p>
              </div>
              {incident.team && (
                <div>
                  <p className="text-sm text-muted-foreground">Team</p>
                  <p className="font-medium">{incident.team}</p>
                </div>
              )}
              {incident.assignee && (
                <div>
                  <p className="text-sm text-muted-foreground">Assignee</p>
                  <div className="flex items-center gap-2">
                    <User className="h-4 w-4" />
                    <span className="font-medium">{incident.assignee}</span>
                  </div>
                </div>
              )}
              {incident.tags && incident.tags.length > 0 && (
                <div>
                  <p className="text-sm text-muted-foreground">Tags</p>
                  <div className="flex flex-wrap gap-1 mt-1">
                    {incident.tags.map((tag) => (
                      <Badge key={tag} variant="secondary">{tag}</Badge>
                    ))}
                  </div>
                </div>
              )}
            </CardContent>
          </Card>

          {/* On-Call */}
          {context?.on_call && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Users className="h-5 w-5" />
                  On-Call
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-3">
                <div className="flex items-center gap-3">
                  <div className="h-10 w-10 rounded-full bg-primary flex items-center justify-center">
                    <User className="h-5 w-5 text-primary-foreground" />
                  </div>
                  <div>
                    <p className="font-medium">{context.on_call.current_responder.name}</p>
                    <p className="text-sm text-muted-foreground">{context.on_call.current_responder.email}</p>
                  </div>
                </div>
                {context.on_call.current_responder.phone && (
                  <Button variant="outline" className="w-full" asChild>
                    <a href={`tel:${context.on_call.current_responder.phone}`}>
                      <Phone className="mr-2 h-4 w-4" />
                      Call
                    </a>
                  </Button>
                )}
              </CardContent>
            </Card>
          )}

          {/* Runbooks */}
          {incident.runbooks && incident.runbooks.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <BookOpen className="h-5 w-5" />
                  Runbooks
                </CardTitle>
              </CardHeader>
              <CardContent className="space-y-2">
                {incident.runbooks.map((runbook) => (
                  <a
                    key={runbook.id}
                    href={runbook.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="flex items-center justify-between rounded-lg border p-3 transition-colors hover:bg-accent"
                  >
                    <span className="font-medium">{runbook.title}</span>
                    <ExternalLink className="h-4 w-4 text-muted-foreground" />
                  </a>
                ))}
              </CardContent>
            </Card>
          )}

          {/* Similar Incidents */}
          {similar && similar.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle className="flex items-center gap-2">
                  <Zap className="h-5 w-5" />
                  Similar Incidents
                </CardTitle>
                <CardDescription>Past incidents with similar patterns</CardDescription>
              </CardHeader>
              <CardContent className="space-y-2">
                {similar.slice(0, 3).map((inc) => (
                  <Link
                    key={inc.id}
                    href={`/incidents/${inc.id}`}
                    className="block rounded-lg border p-3 transition-colors hover:bg-accent"
                  >
                    <p className="font-medium line-clamp-1">{inc.title}</p>
                    <p className="text-sm text-muted-foreground">
                      {inc.resolved_at ? `Resolved ${formatDate(inc.resolved_at)}` : 'Ongoing'}
                    </p>
                  </Link>
                ))}
              </CardContent>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
