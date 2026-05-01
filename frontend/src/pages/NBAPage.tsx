import { useFetch } from '../hooks/useFetch';
import { CardSkeleton, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';

interface NBAData {
  slate: Decision[];
  topOpportunities: Decision[];
  plan: { bet: number; consider: number; skip: number };
  error?: string | null;
}

function BasketballWatermark() {
  return (
    <svg viewBox="0 0 80 80" className="hero-watermark" width="120" height="120" aria-hidden="true">
      <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="3" />
      <line x1="4" y1="40" x2="76" y2="40" stroke="currentColor" strokeWidth="2.5" />
      <line x1="40" y1="4" x2="40" y2="76" stroke="currentColor" strokeWidth="2.5" />
      <path d="M40 4 C52 16, 52 64, 40 76" fill="none" stroke="currentColor" strokeWidth="2.5" />
      <path d="M40 4 C28 16, 28 64, 40 76" fill="none" stroke="currentColor" strokeWidth="2.5" />
    </svg>
  );
}

export default function NBAPage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const { data, loading, error } = useFetch<NBAData>('/api/dashboard/nba');

  const slate = data?.slate ?? [];
  const top = data?.topOpportunities ?? [];
  const plan = data?.plan ?? { bet: 0, consider: 0, skip: 0 };

  return (
    <div className="page-stack">
      <section className="hero-card">
        <BasketballWatermark />
        <p className="page-eyebrow">NBA · Tonight's Slate</p>
        <h1 className="page-title">Tonight&apos;s NBA Plan</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Side, confidence, reason, and trust signal — every game on the slate.
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
            body={data?.error ?? 'Could not load tonight\'s NBA games. Check back shortly.'}
          />
        ) : top.length > 0 ? (
          <div className="grid-2">
            {top.map((decision) => (
              <DecisionCard
                key={`${decision.action}-${decision.side}-${decision.matchup}`}
                decision={decision}
                featured={decision.action === 'BET'}
                onAnalyze={onSelectMatch}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="Slate still forming" body="No NBA games scheduled yet or data is still loading." />
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
          <EmptyState title="No games found" body="No NBA games are available for tonight." />
        ) : null}
      </section>
    </div>
  );
}
