import { useFetch } from '../hooks/useFetch';
import { CardSkeleton, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';

interface SoccerData {
  slate: Decision[];
  topOpportunities: Decision[];
  plan: { bet: number; consider: number; skip: number };
  error?: string | null;
}

function SoccerWatermark() {
  return (
    <svg viewBox="0 0 80 80" className="hero-watermark" width="120" height="120" aria-hidden="true">
      <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="3" />
      <polygon points="40,12 48,30 40,36 32,30" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
      <polygon points="40,36 52,44 48,58 32,58 28,44" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinejoin="round" />
      <line x1="32" y1="30" x2="28" y2="44" stroke="currentColor" strokeWidth="2" />
      <line x1="48" y1="30" x2="52" y2="44" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}

export default function SoccerPage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const { data, loading, error } = useFetch<SoccerData>('/api/dashboard/soccer');

  const slate = data?.slate ?? [];
  const top = data?.topOpportunities ?? [];
  const plan = data?.plan ?? { bet: 0, consider: 0, skip: 0 };

  return (
    <div className="page-stack">
      <section className="hero-card">
        <SoccerWatermark />
        <p className="page-eyebrow">EPL · La Liga · Bundesliga · Serie A</p>
        <h1 className="page-title">Today&apos;s Soccer Plan</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Strongest actions first — scan top picks, then browse the full slate.
        </p>
      </section>

      <PlanStrip bet={plan.bet} consider={plan.consider} skip={plan.skip} />

      <section className="section">
        <div className="section-header">
          <p className="section-label">Top Opportunities</p>
          <div className="section-divider" />
        </div>
        {loading ? (
          <div className="grid-2">
            {[0, 1].map((i) => <CardSkeleton key={i} />)}
          </div>
        ) : error || data?.error ? (
          <EmptyState
            title="Data unavailable"
            body={data?.error ?? 'Could not load today\'s soccer fixtures. Check back shortly.'}
          />
        ) : top.length > 0 ? (
          <div className="grid-2">
            {top.map((decision) => (
              <DecisionCard key={`${decision.action}-${decision.side}-${decision.matchup}`} decision={decision} featured onAnalyze={onSelectMatch} />
            ))}
          </div>
        ) : (
          <EmptyState title="Slate still forming" body="Once fixtures load, the strongest playable sides rise here automatically." />
        )}
      </section>

      <section className="section">
        <div className="section-header">
          <p className="section-label">Full Slate</p>
          <div className="section-divider" />
        </div>
        {loading ? (
          <div className="grid-2">
            {[0, 1, 2, 3].map((i) => <CardSkeleton key={i} />)}
          </div>
        ) : slate.length > 0 ? (
          <div className="grid-2">
            {slate.map((decision) => (
              <DecisionCard key={`${decision.action}-${decision.side}-${decision.matchup}`} decision={decision} onAnalyze={onSelectMatch} />
            ))}
          </div>
        ) : !loading ? (
          <EmptyState title="No fixtures found" body="No soccer matches are available for the current league and date." />
        ) : null}
      </section>
    </div>
  );
}
