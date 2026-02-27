'use client';
import { use } from 'react';
import Link from 'next/link';
import { ArrowLeft, ExternalLink } from 'lucide-react';
import { format } from 'date-fns';
import { SeverityBadge, StatusBadge } from '@/components/StatusBadge';
import ContextCard from '@/components/ContextCard';
import VerdictDisplay from '@/components/VerdictDisplay';
import IncidentTimeline from '@/components/IncidentTimeline';
import { mockIncidents, mockVerdict, mockTimeline } from '@/lib/mock-data';

export default function IncidentDetailPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const incident = mockIncidents.find((i) => i.id === id) || mockIncidents[0];

  return (
    <div className="p-6 md:p-8 space-y-6">
      <Link href="/incidents" className="inline-flex items-center gap-1 text-sm text-gray-500 hover:text-coral transition-colors">
        <ArrowLeft size={16} /> Back to Incidents
      </Link>

      {/* Header */}
      <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <h1 className="font-serif text-2xl md:text-3xl">{incident.id}</h1>
            <SeverityBadge severity={incident.severity} />
            <StatusBadge status={incident.status} />
          </div>
          <p className="text-gray-600">{incident.title}</p>
        </div>
        <div className="text-sm text-gray-500 space-y-1 shrink-0">
          <p>Service: <strong className="text-gray-700">{incident.service}</strong></p>
          <p>Source: {incident.source} {incident.source_url && <a href={incident.source_url} className="text-coral"><ExternalLink size={12} className="inline" /></a>}</p>
          <p>Triggered: {format(new Date(incident.triggered_at), 'MMM d, yyyy HH:mm:ss')}</p>
        </div>
      </div>

      {/* Main content */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 space-y-6">
          <ContextCard verdict={mockVerdict} />
          <IncidentTimeline events={mockTimeline} />
        </div>
        <div className="space-y-6">
          <VerdictDisplay verdict={mockVerdict} />
        </div>
      </div>
    </div>
  );
}
