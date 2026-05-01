import { useState } from 'react';
import { useFetch } from '../hooks/useFetch';
import { CardSkeleton, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';

interface SportData {
  topOpportunities: Decision[];
  slate: Decision[];
  plan: { bet: number; consider: number; skip: number };
}

type SportFilter = 'All' | 'Soccer' | 'NBA';

export default function HomePage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const [sport, setSport] = useState<SportFilter>('All');

  const soccer = useFetch<SportData>('/api/dashboard/soccer');
  const nba = useFetch<SportData>('/api/dashboard/nba');

  const loading = soccer.loading || nba.loading;

  const soccerTop = soccer.data?.topOpportunities ?? [];
  const nbaTop = nba.data?.topOpportunities ?? [];
  const allTop = [...soccerTop, ...nbaTop].sort((a, b) => b.confidence - a.confidence);

  const visible: Decision[] =
    sport === 'Soccer' ? soccerTop :
    sport === 'NBA' ? nbaTop :
    allTop;

  const soccerPlan = soccer.data?.plan ?? { bet: 0, consider: 0, skip: 0 };
  const nbaPlan    = nba.data?.plan    ?? { bet: 0, consider: 0, skip: 0 };
  const activePlan =
    sport === 'Soccer' ? soccerPlan :
    sport === 'NBA'    ? nbaPlan :
    { bet: soccerPlan.bet + nbaPlan.bet, consider: soccerPlan.consider + nbaPlan.consider, skip: soccerPlan.skip + nbaPlan.skip };

  return (
    <div className="page-stack">
      <section className="hero-card">
        <p className="page-eyebrow">Decision Intelligence</p>
        <h1 className="page-title">Clear actions for matchday.</h1>
        <p className="mt-4 max-w-2xl text-slate-400">
          ScorPred ranks every playable matchup with a side, action, confidence context, and the trust signal behind it.
        </p>
      </section>

      <PlanStrip bet={activePlan.bet} consider={activePlan.consider} skip={activePlan.skip} />

      <section className="section">
        <div className="flex items-start justify-between gap-4 flex-wrap">
          <div>
            <p className="section-label">Top Opportunities Today</p>
            <h2 className="font-oswald text-2xl uppercase tracking-[0.08em] text-white">
              Only the strongest data-backed opportunities.
            </h2>
          </div>

          {/* Sport toggle */}
          <div className="flex items-center gap-1 rounded-lg border border-white/[0.08] bg-white/[0.03] p-1">
            {(['All', 'Soccer', 'NBA'] as SportFilter[]).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => setSport(s)}
                className={`rounded-md px-3 py-1.5 text-xs font-semibold uppercase tracking-wider transition ${
                  sport === s
                    ? 'bg-emerald-400/[0.12] text-emerald-300'
                    : 'text-slate-500 hover:text-slate-300'
                }`}
              >
                {s === 'Soccer' ? '⚽ Soccer' : s === 'NBA' ? '🏀 NBA' : 'All'}
              </button>
            ))}
          </div>
        </div>

        {loading ? (
          <div className="grid-2">
            {[0, 1, 2].map((i) => <CardSkeleton key={i} />)}
          </div>
        ) : visible.length > 0 ? (
          <div className="grid-2">
            {visible.slice(0, 6).map((decision) => (
              <DecisionCard
                key={`${decision.action}-${decision.side}-${decision.matchup}`}
                decision={decision}
                featured={decision.confidence >= 65}
                onAnalyze={onSelectMatch}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="Slate still forming" body="Once fixtures load, the strongest playable sides rise here automatically." />
        )}
      </section>
    </div>
  );
}
