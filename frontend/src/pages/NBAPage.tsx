import { useEffect, useState } from 'react';
import { useFetch } from '../hooks/useFetch';
import { CardSkeleton, DateTabs, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';

interface NBAData {
  slate: Decision[];
  topOpportunities: Decision[];
  plan: { bet: number; consider: number; skip: number };
  availableDates?: string[];
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

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function NBAPage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const [selectedDate, setSelectedDate] = useState<string>(todayISO());

  const url = `/api/dashboard/nba?date=${selectedDate}`;
  const { data, loading, error } = useFetch<NBAData>(url, [selectedDate]);

  const availableDates = data?.availableDates ?? [];
  useEffect(() => {
    if (!availableDates.length) return;
    if (!availableDates.includes(selectedDate)) {
      setSelectedDate(availableDates[0]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [availableDates.join(',')]);

  const isTBD = (d: Decision) =>
    !d.teamA || !d.teamB || d.teamA === 'TBD' || d.teamB === 'TBD' ||
    (d.matchup || '').includes('TBD');

  const slate = (data?.slate ?? []).filter(d => !isTBD(d));
  const top   = (data?.topOpportunities ?? []).filter(d => !isTBD(d));
  const plan  = data?.plan ?? { bet: 0, consider: 0, skip: 0 };

  return (
    <div className="page-stack">
      <section className="hero-card">
        <BasketballWatermark />
        <p className="page-eyebrow">NBA · Predictions</p>
        <h1 className="page-title">NBA Game Plan</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Side, confidence, reason, and trust signal — every game on the slate.
        </p>
      </section>

      {/* 3-day date tabs */}
      <DateTabs
        dates={availableDates.length ? availableDates.slice(0, 3) : [todayISO()]}
        selected={selectedDate}
        onSelect={setSelectedDate}
      />

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
            body={data?.error ?? 'Could not load NBA games. Check back shortly.'}
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
          <EmptyState title="No top picks for this day" body="Try another date or check back when games are scheduled." />
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
              <DecisionCard
                key={`${decision.action}-${decision.side}-${decision.matchup}`}
                decision={decision}
                onAnalyze={onSelectMatch}
              />
            ))}
          </div>
        ) : !loading ? (
          <EmptyState title="No games found" body="No NBA games scheduled for this date." />
        ) : null}
      </section>
    </div>
  );
}
