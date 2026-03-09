import { ExternalLink, GitCommit, GitPullRequest, Rocket, Users } from 'lucide-react';
import { format } from 'date-fns';

type GitHubContextData = {
  repo?: string;
  recent_deploys?: Array<{
    short_sha: string;
    message: string;
    author: string;
    timestamp: string;
    url?: string;
  }>;
  codeowners?: string[];
  recent_prs?: Array<{
    number: number;
    title: string;
    author: string;
    merged_at: string;
    url?: string;
  }>;
  recent_deployments?: Array<{
    environment: string;
    status: string;
    created_at: string;
    creator: string;
  }>;
};

export default function GitHubContext({ context }: { context: { github_context?: GitHubContextData } }) {
  const github = context?.github_context;

  if (!github || Object.keys(github).length === 0) {
    return null;
  }

  const commits = github.recent_deploys ?? [];
  const prs = github.recent_prs ?? [];
  const owners = github.codeowners ?? [];
  const deployments = github.recent_deployments ?? [];
  const repoUrl = github.repo
    ? (github.repo.startsWith('http') ? github.repo : `https://github.com/${github.repo}`)
    : null;

  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6 space-y-5">
      <h3 className="font-serif text-lg">GitHub Context</h3>

      {github.repo && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Repository</p>
          {repoUrl ? (
            <a
              href={repoUrl}
              target="_blank"
              rel="noreferrer"
              className="text-sm text-coral hover:underline inline-flex items-center gap-1"
            >
              {github.repo}
              <ExternalLink size={12} />
            </a>
          ) : (
            <p className="text-sm text-gray-800">{github.repo}</p>
          )}
        </div>
      )}

      {commits.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <GitCommit size={14} /> Recent Commits
          </p>
          <ul className="space-y-2">
            {commits.map((commit, idx) => (
              <li key={`${commit.short_sha}-${idx}`} className="text-sm text-gray-700">
                <p className="font-mono text-xs text-blue-600">{commit.short_sha}</p>
                <p className="text-gray-900">{commit.message}</p>
                <p className="text-xs text-gray-500">
                  {commit.author} • {format(new Date(commit.timestamp), 'MMM d, HH:mm')}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {prs.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <GitPullRequest size={14} /> Recent PRs
          </p>
          <ul className="space-y-2">
            {prs.map((pr) => (
              <li key={pr.number} className="text-sm text-gray-700">
                {pr.url ? (
                  <a href={pr.url} target="_blank" rel="noreferrer" className="text-gray-900 hover:underline">
                    #{pr.number} {pr.title}
                  </a>
                ) : (
                  <p className="text-gray-900">#{pr.number} {pr.title}</p>
                )}
                <p className="text-xs text-gray-500">
                  {pr.author} • {format(new Date(pr.merged_at), 'MMM d, HH:mm')}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}

      {owners.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <Users size={14} /> Code Owners
          </p>
          <ul className="space-y-1">
            {owners.map((owner) => (
              <li key={owner} className="text-sm text-gray-700">{owner}</li>
            ))}
          </ul>
        </div>
      )}

      {deployments.length > 0 && (
        <div>
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <Rocket size={14} /> Recent Deployments
          </p>
          <ul className="space-y-2">
            {deployments.map((deploy, idx) => (
              <li key={`${deploy.environment}-${deploy.created_at}-${idx}`} className="text-sm text-gray-700">
                <p className="text-gray-900">
                  {deploy.environment} • {deploy.status}
                </p>
                <p className="text-xs text-gray-500">
                  {deploy.creator} • {format(new Date(deploy.created_at), 'MMM d, HH:mm')}
                </p>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
