import { format } from 'date-fns';
import { Github } from 'lucide-react';
import { GitHubContext } from '@/lib/types';

type GitHubContextCardProps = {
  github_context: Record<string, unknown> | undefined;
  configured: boolean;
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

function asGitHubContext(value: Record<string, unknown> | undefined): GitHubContext {
  if (!value) {
    return {};
  }

  const context: GitHubContext = {};

  if (Array.isArray(value.recent_deploys)) {
    context.recent_deploys = value.recent_deploys
      .filter(isRecord)
      .map((deploy) => ({
        sha: typeof deploy.sha === 'string' ? deploy.sha : undefined,
        environment: typeof deploy.environment === 'string' ? deploy.environment : undefined,
        timestamp: typeof deploy.timestamp === 'string' ? deploy.timestamp : undefined,
      }));
  }

  if (Array.isArray(value.recent_prs)) {
    context.recent_prs = value.recent_prs
      .filter(isRecord)
      .map((pr) => ({
        title: typeof pr.title === 'string' ? pr.title : undefined,
        number: typeof pr.number === 'number' ? pr.number : undefined,
        author: typeof pr.author === 'string' ? pr.author : undefined,
        status: typeof pr.status === 'string' ? pr.status : undefined,
      }));
  }

  if (Array.isArray(value.recent_commits)) {
    context.recent_commits = value.recent_commits
      .filter(isRecord)
      .map((commit) => ({
        message: typeof commit.message === 'string' ? commit.message : undefined,
        sha: typeof commit.sha === 'string' ? commit.sha : undefined,
        author: typeof commit.author === 'string' ? commit.author : undefined,
      }));
  }

  return context;
}

function formatTimestamp(timestamp?: string): string {
  if (!timestamp) {
    return 'Unknown time';
  }

  const parsed = new Date(timestamp);
  if (Number.isNaN(parsed.getTime())) {
    return 'Unknown time';
  }

  return format(parsed, 'MMM d, yyyy HH:mm:ss');
}

function shortSha(sha?: string): string {
  if (!sha) {
    return 'unknown';
  }
  return sha.slice(0, 7);
}

export default function GitHubContextCard({ github_context, configured }: GitHubContextCardProps) {
  if (!configured) {
    return (
      <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-4">
        <div className="flex items-center gap-2 rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-500">
          <Github size={16} className="text-gray-400" />
          <span>GitHub integration not configured</span>
        </div>
      </div>
    );
  }

  const github = asGitHubContext(github_context);
  const hasDeploys = (github.recent_deploys?.length ?? 0) > 0;
  const hasPrs = (github.recent_prs?.length ?? 0) > 0;
  const hasCommits = (github.recent_commits?.length ?? 0) > 0;

  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6 space-y-5">
      <h3 className="font-serif text-lg flex items-center gap-2">
        <Github className="text-coral" size={20} /> GitHub Context
      </h3>

      <section className="space-y-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Recent Deployments</p>
        {hasDeploys ? (
          <ul className="space-y-2">
            {github.recent_deploys?.map((deploy, idx) => (
              <li key={`deploy-${idx}`} className="rounded-lg border border-cream-dark p-3 text-sm text-gray-700">
                <p><span className="font-medium">SHA:</span> <code>{shortSha(deploy.sha)}</code></p>
                <p><span className="font-medium">Environment:</span> {deploy.environment || 'unknown'}</p>
                <p><span className="font-medium">Time:</span> {formatTimestamp(deploy.timestamp)}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400">No recent deployments</p>
        )}
      </section>

      <section className="space-y-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Recent Pull Requests</p>
        {hasPrs ? (
          <ul className="space-y-2">
            {github.recent_prs?.map((pr, idx) => (
              <li key={`pr-${idx}`} className="rounded-lg border border-cream-dark p-3 text-sm text-gray-700">
                <p className="font-medium text-gray-900">{pr.title || 'Untitled PR'}</p>
                <p>#{pr.number ?? 'unknown'} by {pr.author || 'unknown'}</p>
                <p><span className="font-medium">Status:</span> {pr.status || 'unknown'}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400">No recent pull requests</p>
        )}
      </section>

      <section className="space-y-2">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide">Recent Commits</p>
        {hasCommits ? (
          <ul className="space-y-2">
            {github.recent_commits?.map((commit, idx) => (
              <li key={`commit-${idx}`} className="rounded-lg border border-cream-dark p-3 text-sm text-gray-700">
                <p className="font-medium text-gray-900">{commit.message || 'No commit message'}</p>
                <p><code>{shortSha(commit.sha)}</code> by {commit.author || 'unknown'}</p>
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-sm text-gray-400">No recent commits</p>
        )}
      </section>
    </div>
  );
}
