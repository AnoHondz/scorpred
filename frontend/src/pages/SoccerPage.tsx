import { useEffect, useState } from 'react';
import { useFetch } from '../hooks/useFetch';
import { CardSkeleton, DateTabs, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';

interface SoccerData {
  slate: Decision[];
  topOpportunities: Decision[];
  plan: { bet: number; consider: number; skip: number };
  availableDates?: string[];
  selectedDate?: string;
  error?: string | null;
}

interface League {
  id: number;
  name: string;
  flag: string;
  country: string;
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

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function SoccerPage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const [selectedLeagueId, setSelectedLeagueId] = useState<number>(39);
  const [leagues, setLeagues] = useState<League[]>([]);
  const [selectedDate, setSelectedDate] = useState<string>(todayISO());

  useEffect(() => {
    fetch('/api/leagues')
      .then((r) => r.json())
      .then((json) => { if (json.leagues) setLeagues(json.leagues); })
      .catch(() => {});
  }, []);

  const url = `/api/dashboard/soccer?league_id=${selectedLeagueId}&date=${selectedDate}`;
  const { data, loading, error } = useFetch<SoccerData>(url, [selectedLeagueId, selectedDate]);

  const availableDates = data?.availableDates ?? [];
  // Sync to the date the server actually served (handles fallback when today has no games)
  useEffect(() => {
    if (data?.selectedDate && data.selectedDate !== selectedDate) {
      setSelectedDate(data.selectedDate);
    } else if (availableDates.length && !availableDates.includes(selectedDate)) {
      setSelectedDate(availableDates[0]);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data?.selectedDate, availableDates.join(',')]);

  const isTBD = (d: Decision) =>
    !d.teamA || !d.teamB || d.teamA === 'TBD' || d.teamB === 'TBD' ||
    (d.matchup || '').includes('TBD');

  const slate = (data?.slate ?? []).filter(d => !isTBD(d));
  const top   = (data?.topOpportunities ?? []).filter(d => !isTBD(d));
  const plan  = data?.plan ?? { bet: 0, consider: 0, skip: 0 };
  const selectedLeague = leagues.find((l) => l.id === selectedLeagueId);

  return (
    <div className="page-stack">
      <section className="hero-card">
        <SoccerWatermark />
        <p className="page-eyebrow">
          {selectedLeague ? `${selectedLeague.flag} ${selectedLeague.name}` : 'Soccer'}
        </p>
        <h1 className="page-title">Soccer Predictions</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Strongest actions first — scan top picks, then browse the full slate.
        </p>
      </section>

      {/* League switcher */}
      {leagues.length > 0 && (
        <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
          {leagues.map((lg) => (
            <button
              key={lg.id}
              type="button"
              onClick={() => { setSelectedLeagueId(lg.id); setSelectedDate(todayISO()); }}
              className={`flex-shrink-0 flex items-center gap-1.5 rounded-full border px-3.5 py-1.5 text-[12px] font-semibold transition
                ${selectedLeagueId === lg.id
                  ? 'border-teal-500/50 bg-teal-500/[0.12] text-teal-300'
                  : 'border-white/[0.08] bg-white/[0.03] text-slate-500 hover:border-white/20 hover:text-slate-300'
                }`}
            >
              <span>{lg.flag}</span>
              <span>{lg.name}</span>
            </button>
          ))}
        </div>
      )}

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
            body={data?.error ?? "Could not load soccer fixtures. Check back shortly."}
          />
        ) : top.length > 0 ? (
          <div className="grid-2">
            {top.map((decision) => (
              <DecisionCard
                key={`${decision.action}-${decision.side}-${decision.matchup}`}
                decision={decision}
                featured
                onAnalyze={onSelectMatch}
              />
            ))}
          </div>
        ) : (
          <EmptyState title="No top picks for this day" body="Try another date or check back when fixtures are confirmed." />
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
          <EmptyState title="No fixtures" body="No matches found for this date and league." />
        ) : null}
      </section>
    </div>
  );
}
