import { format } from 'date-fns';
import { GitCommitHorizontal, GitPullRequest, Rocket } from 'lucide-react';

interface GitHubContextCardProps {
  githubContext: Record<string, unknown>;
}

function asRecord(value: unknown): Record<string, unknown> | null {
  return value && typeof value === 'object' ? (value as Record<string, unknown>) : null;
}

function asRecordList(value: unknown): Record<string, unknown>[] {
  if (!Array.isArray(value)) return [];
  return value
    .map((item) => asRecord(item))
    .filter((item): item is Record<string, unknown> => item !== null);
}

function formatDate(value: unknown): string {
  if (typeof value !== 'string') return 'Unknown date';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Unknown date';
  return format(date, 'MMM d, yyyy HH:mm');
}

function formatSha(commit: Record<string, unknown>): string {
  const shortSha = typeof commit.short_sha === 'string' ? commit.short_sha : '';
  if (shortSha) return shortSha;
  const sha = typeof commit.sha === 'string' ? commit.sha : '';
  return sha ? sha.slice(0, 12) : 'unknown';
}

export default function GitHubContextCard({ githubContext }: GitHubContextCardProps) {
  const commits = asRecordList(githubContext.recent_deploys).slice(0, 5);
  const prs = asRecordList(githubContext.recent_prs).slice(0, 5);
  const deployments = asRecordList(githubContext.recent_deployments).slice(0, 5);

  if (!commits.length && !prs.length && !deployments.length) {
    return null;
  }

  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6 space-y-6">
      <h3 className="font-serif text-lg">GitHub Context</h3>

      {commits.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
            <GitCommitHorizontal size={14} className="text-blue-600" /> Recent Commits
          </h4>
          <div className="space-y-2">
            {commits.map((commit, idx) => {
              const sha = formatSha(commit);
              const author = typeof commit.author === 'string' ? commit.author : 'unknown';
              const message = typeof commit.message === 'string' ? commit.message : 'Code change';
              return (
                <div key={`${sha}-${idx}`} className="rounded-md border border-cream-dark p-3 text-sm">
                  <p className="font-mono text-blue-700">{sha}</p>
                  <p className="text-gray-800 mt-0.5">{message}</p>
                  <p className="text-xs text-gray-500 mt-1">Author: {author}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {prs.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
            <GitPullRequest size={14} className="text-coral-dark" /> Recent PRs
          </h4>
          <div className="space-y-2">
            {prs.map((pr, idx) => {
              const number = typeof pr.number === 'number' ? pr.number : typeof pr.number === 'string' ? pr.number : 'unknown';
              const title = typeof pr.title === 'string' ? pr.title : 'Pull request';
              const author = typeof pr.author === 'string' ? pr.author : 'unknown';
              return (
                <div key={`${number}-${idx}`} className="rounded-md border border-cream-dark p-3 text-sm">
                  <p className="text-coral-dark font-semibold">#{number}</p>
                  <p className="text-gray-800 mt-0.5">{title}</p>
                  <p className="text-xs text-gray-500 mt-1">
                    Author: {author} | Merged: {formatDate(pr.merged_at)}
                  </p>
                </div>
              );
            })}
          </div>
        </div>
      )}

      {deployments.length > 0 && (
        <div>
          <h4 className="text-sm font-semibold text-gray-700 uppercase tracking-wide mb-2 flex items-center gap-2">
            <Rocket size={14} className="text-green-600" /> Recent Deployments
          </h4>
          <div className="space-y-2">
            {deployments.map((deployment, idx) => {
              const environment = typeof deployment.environment === 'string' ? deployment.environment : 'unknown';
              const status = typeof deployment.status === 'string' ? deployment.status : 'unknown';
              return (
                <div key={`${environment}-${idx}`} className="rounded-md border border-cream-dark p-3 text-sm">
                  <p className="text-gray-800">
                    <span className="font-semibold">{environment}</span> ({status})
                  </p>
                  <p className="text-xs text-gray-500 mt-1">Date: {formatDate(deployment.created_at)}</p>
                </div>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
