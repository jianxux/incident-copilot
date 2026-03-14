import { TimelineEvent } from '@/lib/types';
import {
  Bell,
  CheckCircle,
  Eye,
  GitCommit,
  GitPullRequest,
  MessageSquare,
  Rocket,
  Search,
  Wrench,
} from 'lucide-react';
import { format } from 'date-fns';

const iconMap: Record<string, typeof Bell> = {
  alert: Bell,
  investigation: Search,
  action: Wrench,
  resolution: CheckCircle,
  created: Bell,
  acknowledged: Eye,
  resolved: CheckCircle,
  comment: MessageSquare,
  code_change: GitCommit,
  pull_request: GitPullRequest,
  deployment: Rocket,
};

const colorMap: Record<string, string> = {
  alert: 'bg-red-500',
  investigation: 'bg-blue-500',
  action: 'bg-coral',
  resolution: 'bg-green-500',
  created: 'bg-red-500',
  acknowledged: 'bg-amber-500',
  resolved: 'bg-green-500',
  comment: 'bg-blue-500',
  code_change: 'bg-purple-500',
  pull_request: 'bg-indigo-500',
  deployment: 'bg-purple-500',
};

function formatEventType(eventType: string): string {
  return eventType.replace(/_/g, ' ').replace(/\b\w/g, (letter) => letter.toUpperCase());
}

export default function IncidentTimeline({ events }: { events: TimelineEvent[] }) {
  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6">
      <h3 className="font-serif text-lg mb-4">Timeline</h3>
      <div className="relative">
        <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
        <div className="space-y-6">
          {events.map((event) => {
            const Icon = iconMap[event.type] || Bell;
            const title = event.title || formatEventType(event.type);
            return (
              <div key={event.id} className="relative flex gap-4 pl-0">
                <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white z-10 ${colorMap[event.type] || 'bg-gray-400'}`}>
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0 pb-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-gray-900">{title}</p>
                    <span className="text-xs text-gray-400">{format(new Date(event.timestamp), 'HH:mm:ss')}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-0.5">{event.description}</p>
                  {event.actor ? <p className="text-xs text-gray-500 mt-1">By {event.actor}</p> : null}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
