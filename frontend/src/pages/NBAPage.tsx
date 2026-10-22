import { navigate, useLocation, localToday } from '../navigation';
import RequestError from '../components/RequestError';
import { useFetch } from '../hooks/useFetch';
import { useNow } from '../hooks/useNow';
import { decisionAt } from '../decisionLifecycle';
import { slatePlan } from '../slate';
import { CardSkeleton, DateTabs, DecisionCard, EmptyState, PlanStrip, type Decision } from '../components/DecisionCard';
import DataStatus from '../components/DataStatus';
import { MatchupStage } from '../components/immersive/CommandCenter';
import NBAContext from '../components/NBAContext';

interface NBAData {
  slate: Decision[];
  topOpportunities: Decision[];
  plan: { bet: number; consider: number; skip: number };
  availableDates?: string[];
  selectedDate?: string;
  error?: string | null;
  warnings?: string[];
  last_updated?: string | null;
  notice?: string;
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

const todayISO = localToday;

export default function NBAPage({ onSelectMatch }: { onSelectMatch: (d: Decision) => void }) {
  const now = useNow();
  const location = useLocation();
  const params = new URLSearchParams(location.split('?')[1]);
  const view = params.get('view') || 'upcoming';
  const requestedDate = params.get('date') || '';
  const url = view === 'upcoming' ? `/api/dashboard/nba?date=${requestedDate}` : `/api/nba/games?view=${view}&date=${requestedDate}`;
  const { data, loading, error, retry } = useFetch<NBAData>(url);
  const availableDates = data?.availableDates ?? [];
  const selectedDate = requestedDate || data?.selectedDate || availableDates[0] || todayISO();
  const setSelectedDate = (date: string) => navigate(`/nba?view=${view}&date=${date}`);

  const isTBD = (d: Decision) =>
    !d.teamA || !d.teamB || d.teamA === 'TBD' || d.teamB === 'TBD' ||
    (d.matchup || '').includes('TBD');

  const slate = (data?.slate ?? []).map(card => decisionAt(card, now)).filter(d => !isTBD(d));
  const top = (data?.topOpportunities ?? []).map(card => decisionAt(card, now)).filter(d => !isTBD(d) && d.action !== 'SKIP');
  const plan = slatePlan(slate);

  return (
    <div className="page-stack">
      <section className="hero-card">
        <BasketballWatermark />
        <p className="page-eyebrow">NBA · Predictions</p>
        <h1 className="page-title">NBA Game Plan</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Browse the schedule and compare available matchup analysis.
        </p>
      </section>

      {error && <RequestError message={error} onRetry={retry} />}
      {data?.error && <RequestError message={data.error} onRetry={retry} />}
      <div className="dashboard-controls"><div className="sport-filter" aria-label="NBA schedule view">
        {(['upcoming', 'results', 'archive'] as const).map(item => <button key={item} aria-pressed={view === item} onClick={() => {
          const yesterday = new Date(`${todayISO()}T12:00:00Z`); yesterday.setUTCDate(yesterday.getUTCDate() - 1);
          navigate(item === 'upcoming' ? '/nba' : `/nba?view=${item}${item === 'results' ? `&date=${yesterday.toISOString().slice(0, 10)}` : ''}`);
        }}>{item === 'upcoming' ? 'Upcoming' : item === 'results' ? 'Recent results' : 'Local history'}</button>)}
      </div>{view !== 'upcoming' && <label className="quiet-label">Observation date <input type="date" aria-label="NBA observation date" value={selectedDate} onChange={event => { if (event.target.value) setSelectedDate(event.target.value); }} /></label>}</div>
      {data?.notice && <p className="coverage-note">{data.notice}</p>}
      <DateTabs
        dates={[...new Set([...(availableDates.length ? availableDates : [todayISO()]), selectedDate])].sort()}
        selected={selectedDate}
        onSelect={setSelectedDate}
      />

      {slate[0] && <div className="section">
        <NBAContext key={`${view}-${slate[0].matchId}`} decision={slate[0]} compact />
        <button className="btn-analyze" onClick={() => onSelectMatch(slate[0])}>Open full comparison: {slate[0].matchup}</button>
      </div>}

      <MatchupStage sport="nba" decision={slate[0]} onSelect={onSelectMatch} label={view === 'upcoming' ? 'COURTSIDE INTELLIGENCE' : 'RECORDED OBSERVATIONS'} />

      <PlanStrip bet={plan.bet} consider={plan.consider} skip={plan.skip} loading={loading} />
      <DataStatus cards={slate} updated={data?.last_updated} loading={loading} warnings={data?.warnings} />

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
        ) : !loading && !error && !data?.error ? (
          <EmptyState title="No games found" body="No NBA games scheduled for this date." />
        ) : null}
      </section>
      {top.length > 0 && (
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
      )}
    </div>
  );
}
