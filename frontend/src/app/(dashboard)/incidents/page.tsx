'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useIncidents, useAcknowledgeIncident, useResolveIncident } from '@/hooks/use-incidents';
import { useAppStore } from '@/lib/store';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Skeleton } from '@/components/ui/skeleton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
  DropdownMenuSeparator,
  DropdownMenuLabel,
} from '@/components/ui/dropdown-menu';
import { formatDate, formatDuration, cn } from '@/lib/utils';
import { Incident, Severity, Status } from '@/types/incident';
import {
  AlertTriangle,
  CheckCircle,
  ChevronDown,
  Clock,
  Eye,
  Filter,
  LayoutGrid,
  List,
  MoreHorizontal,
  Search,
  SortAsc,
  X,
} from 'lucide-react';

const severityOptions: Severity[] = ['critical', 'high', 'medium', 'low', 'info'];
const statusOptions: Status[] = ['triggered', 'acknowledged', 'resolved'];

export default function IncidentsPage() {
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const { incidentFilters, setIncidentFilters, incidentView, setIncidentView } = useAppStore();
  
  const { data, isLoading, error } = useIncidents(
    { ...incidentFilters, search: search || undefined },
    page,
    20
  );
  
  const acknowledgeIncident = useAcknowledgeIncident();
  const resolveIncident = useResolveIncident();

  const toggleSeverityFilter = (severity: Severity) => {
    const current = incidentFilters.severity || [];
    const updated = current.includes(severity)
      ? current.filter((s) => s !== severity)
      : [...current, severity];
    setIncidentFilters({ ...incidentFilters, severity: updated.length ? updated : undefined });
  };

  const toggleStatusFilter = (status: Status) => {
    const current = incidentFilters.status || [];
    const updated = current.includes(status)
      ? current.filter((s) => s !== status)
      : [...current, status];
    setIncidentFilters({ ...incidentFilters, status: updated.length ? updated : undefined });
  };

  const clearFilters = () => {
    setIncidentFilters({});
    setSearch('');
  };

  const hasFilters = 
    (incidentFilters.severity?.length ?? 0) > 0 ||
    (incidentFilters.status?.length ?? 0) > 0 ||
    search;

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold">Incidents</h1>
          <p className="text-muted-foreground">
            Manage and track all incidents across your services
          </p>
        </div>
        <Button asChild>
          <Link href="/incidents/new">
            <AlertTriangle className="mr-2 h-4 w-4" />
            Create Incident
          </Link>
        </Button>
      </div>

      {/* Filters */}
      <Card>
        <CardContent className="p-4">
          <div className="flex flex-wrap items-center gap-4">
            {/* Search */}
            <div className="relative flex-1 min-w-[200px]">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                placeholder="Search incidents..."
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                className="pl-10"
              />
            </div>

            {/* Severity filter */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="gap-2">
                  <Filter className="h-4 w-4" />
                  Severity
                  {incidentFilters.severity?.length ? (
                    <Badge variant="secondary" className="ml-1">
                      {incidentFilters.severity.length}
                    </Badge>
                  ) : null}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuLabel>Filter by severity</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {severityOptions.map((severity) => (
                  <DropdownMenuItem
                    key={severity}
                    onClick={() => toggleSeverityFilter(severity)}
                    className="gap-2"
                  >
                    <div
                      className={cn(
                        'h-3 w-3 rounded-full',
                        incidentFilters.severity?.includes(severity) && 'ring-2 ring-offset-2'
                      )}
                      style={{
                        backgroundColor: {
                          critical: '#dc2626',
                          high: '#ea580c',
                          medium: '#ca8a04',
                          low: '#2563eb',
                          info: '#6b7280',
                        }[severity],
                      }}
                    />
                    <span className="capitalize">{severity}</span>
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Status filter */}
            <DropdownMenu>
              <DropdownMenuTrigger asChild>
                <Button variant="outline" className="gap-2">
                  <Filter className="h-4 w-4" />
                  Status
                  {incidentFilters.status?.length ? (
                    <Badge variant="secondary" className="ml-1">
                      {incidentFilters.status.length}
                    </Badge>
                  ) : null}
                  <ChevronDown className="h-4 w-4" />
                </Button>
              </DropdownMenuTrigger>
              <DropdownMenuContent align="start">
                <DropdownMenuLabel>Filter by status</DropdownMenuLabel>
                <DropdownMenuSeparator />
                {statusOptions.map((status) => (
                  <DropdownMenuItem
                    key={status}
                    onClick={() => toggleStatusFilter(status)}
                    className="gap-2"
                  >
                    <StatusIcon status={status} />
                    <span className="capitalize">{status}</span>
                    {incidentFilters.status?.includes(status) && (
                      <CheckCircle className="ml-auto h-4 w-4" />
                    )}
                  </DropdownMenuItem>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>

            {/* Clear filters */}
            {hasFilters && (
              <Button variant="ghost" size="sm" onClick={clearFilters}>
                <X className="mr-2 h-4 w-4" />
                Clear filters
              </Button>
            )}

            {/* View toggle */}
            <div className="ml-auto flex items-center gap-1 rounded-lg border p-1">
              <Button
                variant={incidentView === 'list' ? 'secondary' : 'ghost'}
                size="icon"
                className="h-8 w-8"
                onClick={() => setIncidentView('list')}
              >
                <List className="h-4 w-4" />
              </Button>
              <Button
                variant={incidentView === 'grid' ? 'secondary' : 'ghost'}
                size="icon"
                className="h-8 w-8"
                onClick={() => setIncidentView('grid')}
              >
                <LayoutGrid className="h-4 w-4" />
              </Button>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Results info */}
      <div className="flex items-center justify-between text-sm text-muted-foreground">
        <span>
          {data?.total ?? 0} incidents found
          {hasFilters && ' (filtered)'}
        </span>
        <Button variant="ghost" size="sm">
          <SortAsc className="mr-2 h-4 w-4" />
          Sort by: Created
        </Button>
      </div>

      {/* Incidents list */}
      {isLoading ? (
        <div className="space-y-4">
          {[...Array(5)].map((_, i) => (
            <Skeleton key={i} className="h-24" />
          ))}
        </div>
      ) : error ? (
        <Card>
          <CardContent className="py-10 text-center">
            <p className="text-destructive">Failed to load incidents</p>
            <Button variant="outline" className="mt-4" onClick={() => window.location.reload()}>
              Retry
            </Button>
          </CardContent>
        </Card>
      ) : data?.incidents?.length === 0 ? (
        <Card>
          <CardContent className="py-16 text-center">
            <AlertTriangle className="mx-auto h-12 w-12 text-muted-foreground" />
            <h3 className="mt-4 text-lg font-semibold">No incidents found</h3>
            <p className="text-muted-foreground">
              {hasFilters
                ? 'Try adjusting your filters'
                : 'No incidents have been created yet'}
            </p>
          </CardContent>
        </Card>
      ) : incidentView === 'grid' ? (
        <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
          {data?.incidents.map((incident) => (
            <IncidentCard
              key={incident.id}
              incident={incident}
              onAcknowledge={() => acknowledgeIncident.mutate(incident.id)}
              onResolve={() => resolveIncident.mutate({ id: incident.id })}
            />
          ))}
        </div>
      ) : (
        <div className="space-y-2">
          {data?.incidents.map((incident) => (
            <IncidentRow
              key={incident.id}
              incident={incident}
              onAcknowledge={() => acknowledgeIncident.mutate(incident.id)}
              onResolve={() => resolveIncident.mutate({ id: incident.id })}
            />
          ))}
        </div>
      )}

      {/* Pagination */}
      {(data?.total ?? 0) > 20 && (
        <div className="flex items-center justify-center gap-2">
          <Button
            variant="outline"
            disabled={page === 1}
            onClick={() => setPage(page - 1)}
          >
            Previous
          </Button>
          <span className="text-sm text-muted-foreground">
            Page {page} of {Math.ceil((data?.total ?? 0) / 20)}
          </span>
          <Button
            variant="outline"
            disabled={page * 20 >= (data?.total ?? 0)}
            onClick={() => setPage(page + 1)}
          >
            Next
          </Button>
        </div>
      )}
    </div>
  );
}

function StatusIcon({ status }: { status: Status }) {
  switch (status) {
    case 'triggered':
      return <AlertTriangle className="h-4 w-4 text-red-500" />;
    case 'acknowledged':
      return <Eye className="h-4 w-4 text-yellow-500" />;
    case 'resolved':
      return <CheckCircle className="h-4 w-4 text-green-500" />;
    default:
      return <Clock className="h-4 w-4 text-muted-foreground" />;
  }
}

interface IncidentItemProps {
  incident: Incident;
  onAcknowledge: () => void;
  onResolve: () => void;
}

function IncidentCard({ incident, onAcknowledge, onResolve }: IncidentItemProps) {
  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="pb-2">
        <div className="flex items-start justify-between">
          <Badge variant={incident.severity as any}>{incident.severity}</Badge>
          <IncidentActions
            incident={incident}
            onAcknowledge={onAcknowledge}
            onResolve={onResolve}
          />
        </div>
      </CardHeader>
      <CardContent>
        <Link href={`/incidents/${incident.id}`} className="block space-y-2">
          <h3 className="font-semibold line-clamp-2 hover:underline">
            {incident.title}
          </h3>
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Badge variant="service">{incident.service}</Badge>
            <span>•</span>
            <StatusIcon status={incident.status} />
            <span className="capitalize">{incident.status}</span>
          </div>
          <div className="flex items-center gap-2 text-xs text-muted-foreground">
            <Clock className="h-3 w-3" />
            {formatDate(incident.created_at)}
            {incident.ttr && (
              <>
                <span>•</span>
                <span>TTR: {formatDuration(incident.ttr)}</span>
              </>
            )}
          </div>
        </Link>
      </CardContent>
    </Card>
  );
}

function IncidentRow({ incident, onAcknowledge, onResolve }: IncidentItemProps) {
  return (
    <div className="flex items-center gap-4 rounded-lg border p-4 transition-colors hover:bg-accent">
      <div className={cn(
        'h-3 w-3 rounded-full',
        incident.status === 'triggered' && 'animate-pulse'
      )} style={{
        backgroundColor: {
          critical: '#dc2626',
          high: '#ea580c',
          medium: '#ca8a04',
          low: '#2563eb',
          info: '#6b7280',
        }[incident.severity],
      }} />
      
      <Link href={`/incidents/${incident.id}`} className="flex-1 min-w-0">
        <div className="flex items-center gap-2">
          <span className="font-medium truncate">{incident.title}</span>
        </div>
        <div className="flex items-center gap-2 text-sm text-muted-foreground">
          <Badge variant="service" className="text-xs">{incident.service}</Badge>
          <span>•</span>
          <span>{formatDate(incident.created_at)}</span>
        </div>
      </Link>

      <div className="flex items-center gap-2">
        <Badge variant={incident.status === 'triggered' ? 'destructive' : incident.status === 'acknowledged' ? 'warning' : 'success'}>
          {incident.status}
        </Badge>
        <IncidentActions
          incident={incident}
          onAcknowledge={onAcknowledge}
          onResolve={onResolve}
        />
      </div>
    </div>
  );
}

function IncidentActions({ incident, onAcknowledge, onResolve }: IncidentItemProps) {
  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button variant="ghost" size="icon" className="h-8 w-8">
          <MoreHorizontal className="h-4 w-4" />
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end">
        <DropdownMenuItem asChild>
          <Link href={`/incidents/${incident.id}`}>
            View details
          </Link>
        </DropdownMenuItem>
        {incident.status === 'triggered' && (
          <DropdownMenuItem onClick={onAcknowledge}>
            <Eye className="mr-2 h-4 w-4" />
            Acknowledge
          </DropdownMenuItem>
        )}
        {incident.status !== 'resolved' && (
          <DropdownMenuItem onClick={onResolve}>
            <CheckCircle className="mr-2 h-4 w-4" />
            Resolve
          </DropdownMenuItem>
        )}
        <DropdownMenuSeparator />
        <DropdownMenuItem>Add note</DropdownMenuItem>
        <DropdownMenuItem>Escalate</DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
