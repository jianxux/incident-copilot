import Link from 'next/link';
import { Shield, Zap, Clock, BarChart3, ArrowRight } from 'lucide-react';

const features = [
  { icon: Zap, title: 'Auto-Context Assembly', desc: 'Automatically gathers logs, metrics, deployments, and topology when alerts fire.' },
  { icon: Clock, title: '30s Time-to-Context', desc: 'Compressed context cards delivered in under 30 seconds from alert trigger.' },
  { icon: Shield, title: 'AI-Powered Verdicts', desc: 'Claude-powered analysis identifies root causes with confidence scoring.' },
  { icon: BarChart3, title: 'MTTR Reduction', desc: 'Teams see 30%+ reduction in mean time to resolution within weeks.' },
];

export default function LandingPage() {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden bg-sidebar text-white">
        <div className="max-w-5xl mx-auto px-6 py-24 md:py-32 text-center">
          <div className="flex justify-center mb-6">
            <Shield className="text-coral" size={48} />
          </div>
          <h1 className="font-serif text-4xl md:text-6xl mb-4">Incident Copilot</h1>
          <p className="text-lg md:text-xl text-gray-300 max-w-2xl mx-auto mb-8">
            AI-powered incident analysis that auto-assembles context so your on-call engineers can resolve faster.
          </p>
          <div className="flex flex-col sm:flex-row gap-4 justify-center">
            <Link
              href="/dashboard"
              className="inline-flex items-center gap-2 bg-coral hover:bg-coral-dark text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              Go to Dashboard <ArrowRight size={18} />
            </Link>
            <Link
              href="/incidents"
              className="inline-flex items-center gap-2 border border-white/20 hover:bg-white/10 text-white px-6 py-3 rounded-lg font-medium transition-colors"
            >
              View Incidents
            </Link>
          </div>
        </div>
      </section>

      {/* Features */}
      <section className="max-w-5xl mx-auto px-6 py-16">
        <h2 className="font-serif text-3xl text-center mb-12">How it works</h2>
        <div className="grid grid-cols-1 md:grid-cols-2 gap-8">
          {features.map(({ icon: Icon, title, desc }) => (
            <div key={title} className="bg-white rounded-xl border border-cream-dark p-6 shadow-sm">
              <Icon className="text-coral mb-3" size={28} />
              <h3 className="font-serif text-xl mb-2">{title}</h3>
              <p className="text-sm text-gray-600">{desc}</p>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
