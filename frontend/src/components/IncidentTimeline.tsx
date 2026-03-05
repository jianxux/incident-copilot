import { TimelineEvent } from '@/lib/types';
import { Bell, Search, Wrench, CheckCircle, Rocket, GitCommit, GitPullRequest } from 'lucide-react';
import { format } from 'date-fns';

const iconMap: Record<string, typeof Bell> = {
  alert: Bell,
  investigation: Search,
  action: Wrench,
  resolution: CheckCircle,
  deployment: Rocket,
  code_change: GitCommit,
  pull_request: GitPullRequest,
};

const colorMap: Record<string, string> = {
  alert: 'bg-red-500',
  investigation: 'bg-blue-500',
  action: 'bg-coral',
  resolution: 'bg-green-500',
  deployment: 'bg-purple-500',
  code_change: 'bg-orange-500',
  pull_request: 'bg-cyan-500',
};

export default function IncidentTimeline({ events }: { events: TimelineEvent[] }) {
  const getMetadataValue = (event: TimelineEvent, keys: string[]): string | undefined => {
    if (!event.metadata) {
      return undefined;
    }

    for (const key of keys) {
      const value = event.metadata[key];
      if (typeof value === 'string' && value.trim()) {
        return value;
      }
      if (typeof value === 'number') {
        return String(value);
      }
    }

    return undefined;
  };

  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6">
      <h3 className="font-serif text-lg mb-4">Timeline</h3>
      <div className="relative">
        <div className="absolute left-4 top-0 bottom-0 w-0.5 bg-gray-200" />
        <div className="space-y-6">
          {events.map((event) => {
            const Icon = iconMap[event.type] || Bell;
            return (
              <div key={event.id} className="relative flex gap-4 pl-0">
                <div className={`shrink-0 w-8 h-8 rounded-full flex items-center justify-center text-white z-10 ${colorMap[event.type] || 'bg-gray-400'}`}>
                  <Icon size={14} />
                </div>
                <div className="flex-1 min-w-0 pb-1">
                  <div className="flex items-center gap-2 flex-wrap">
                    <p className="text-sm font-semibold text-gray-900">{event.title}</p>
                    <span className="text-xs text-gray-400">{format(new Date(event.timestamp), 'HH:mm:ss')}</span>
                  </div>
                  <p className="text-sm text-gray-600 mt-0.5">{event.description}</p>
                  {(event.type === 'code_change' || event.type === 'pull_request') && (
                    <div className="mt-2 flex items-center gap-2 flex-wrap text-xs text-gray-500">
                      {event.type === 'code_change' && getMetadataValue(event, ['sha', 'commit_sha']) && (
                        <span className="rounded bg-gray-100 px-2 py-0.5">
                          SHA: <code>{getMetadataValue(event, ['sha', 'commit_sha'])?.slice(0, 7)}</code>
                        </span>
                      )}
                      {event.type === 'pull_request' && getMetadataValue(event, ['pr_number', 'number']) && (
                        <span className="rounded bg-gray-100 px-2 py-0.5">
                          PR #{getMetadataValue(event, ['pr_number', 'number'])}
                        </span>
                      )}
                      {getMetadataValue(event, ['author']) && (
                        <span className="rounded bg-gray-100 px-2 py-0.5">
                          Author: {getMetadataValue(event, ['author'])}
                        </span>
                      )}
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
