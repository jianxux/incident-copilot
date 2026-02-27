import { Verdict } from '@/lib/types';
import { Brain, RotateCcw } from 'lucide-react';

export default function VerdictDisplay({ verdict }: { verdict: Verdict }) {
  return (
    <div className="bg-white rounded-xl border border-cream-dark shadow-sm p-6 space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="font-serif text-lg flex items-center gap-2">
          <Brain className="text-coral" size={20} /> AI Verdict
        </h3>
        <div className="flex items-center gap-2">
          <div className="w-20 h-2 bg-gray-200 rounded-full overflow-hidden">
            <div
              className="h-full bg-coral rounded-full"
              style={{ width: `${verdict.confidence}%` }}
            />
          </div>
          <span className="text-sm font-semibold text-coral">{verdict.confidence}%</span>
        </div>
      </div>

      <div>
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wide mb-1">Root Cause Hypothesis</p>
        <p className="text-gray-800 text-sm leading-relaxed">{verdict.root_cause_hypothesis}</p>
      </div>

      {verdict.rollback_recommended && (
        <div className="flex items-center gap-3 bg-red-50 border border-red-200 rounded-lg px-4 py-3">
          <RotateCcw className="text-red-600 shrink-0" size={18} />
          <div>
            <p className="text-sm font-semibold text-red-700">Rollback Recommended</p>
            <p className="text-xs text-red-600">Target: <code className="bg-red-100 px-1 rounded">{verdict.rollback_target}</code></p>
          </div>
        </div>
      )}
    </div>
  );
}
