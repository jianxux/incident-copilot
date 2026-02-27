import { Verdict } from '@/lib/types';
import { FileText, Lightbulb, ListChecks } from 'lucide-react';

export default function ContextCard({ verdict }: { verdict: Verdict }) {
  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm overflow-hidden">
      <div className="bg-coral px-6 py-4">
        <h3 className="text-white font-serif text-lg flex items-center gap-2">
          <FileText size={20} /> Incident Analysis
        </h3>
      </div>
      <div className="p-6 space-y-5">
        <div>
          <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-1">Summary</p>
          <p className="text-gray-800">{verdict.summary}</p>
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <Lightbulb size={14} /> Key Findings
          </p>
          <ul className="space-y-1">
            {verdict.key_findings.map((f, i) => (
              <li key={i} className="flex items-start gap-2 text-sm text-gray-700">
                <span className="text-coral mt-0.5">•</span> {f}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <p className="text-sm font-semibold text-gray-500 uppercase tracking-wide mb-2 flex items-center gap-1">
            <ListChecks size={14} /> Recommended Actions
          </p>
          <ol className="space-y-1 list-decimal list-inside">
            {verdict.recommended_actions.map((a, i) => (
              <li key={i} className="text-sm text-gray-700">{a}</li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
