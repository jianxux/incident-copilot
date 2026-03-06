import { TimelineEvent } from '@/lib/types';
import { Bell, Search, Wrench, CheckCircle, Rocket, GitCommitHorizontal, GitPullRequest } from 'lucide-react';
import { format } from 'date-fns';

const iconMap: Record<string, typeof Bell> = {
  alert: Bell,
  investigation: Search,
  action: Wrench,
  resolution: CheckCircle,
  code_change: GitCommitHorizontal,
  pull_request: GitPullRequest,
  deployment: Rocket,
};

const colorMap: Record<string, string> = {
  alert: 'bg-red-500',
  investigation: 'bg-blue-500',
  action: 'bg-coral',
  resolution: 'bg-green-500',
  code_change: 'bg-blue-600',
  pull_request: 'bg-coral-dark',
  deployment: 'bg-green-600',
};

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null;
}

function toTitleCase(value: string): string {
  return value.replace(/_/g, ' ').replace(/\b\w/g, (c: string) => c.toUpperCase());
}

function formatSha(commit: Record<string, unknown> | null): string {
  const shortSha = typeof commit?.short_sha === 'string' ? commit.short_sha : '';
  if (shortSha) return shortSha;
  const sha = typeof commit?.sha === 'string' ? commit.sha : '';
  return sha ? sha.slice(0, 12) : 'unknown';
}

function renderGithubDetails(event: TimelineEvent): string | null {
  const metadata = asRecord(event.metadata);

  if (event.type === 'code_change') {
    const commit = asRecord(metadata?.commit);
    if (!commit) return null;
    const sha = formatSha(commit);
    const message = typeof commit.message === 'string' ? commit.message : 'Code change';
    return `${sha} - ${message}`;
  }

  if (event.type === 'pull_request') {
    const pr = asRecord(metadata?.pull_request);
    if (!pr) return null;
    const number = typeof pr.number === 'number' ? pr.number : typeof pr.number === 'string' ? Number(pr.number) : NaN;
    const title = typeof pr.title === 'string' ? pr.title : 'Pull request';
    return Number.isFinite(number) ? `PR #${number} - ${title}` : title;
  }

  if (event.type === 'deployment') {
    const deployment = asRecord(metadata?.deployment);
    if (!deployment) return null;
    const environment = typeof deployment.environment === 'string' ? deployment.environment : 'unknown';
    const status = typeof deployment.status === 'string' ? deployment.status : 'unknown';
    return `${environment} - ${status}`;
  }

  return null;
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
            const githubDetails = renderGithubDetails(event);
            const title = event.title || toTitleCase(event.type);

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
                  {githubDetails && <p className="text-xs text-gray-500 mt-1 font-mono">{githubDetails}</p>}
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </div>
  );
}
