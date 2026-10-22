import { ArrowUpRight, Eye, Layers3, Pause, Target } from 'lucide-react';
import { calendarFormat, dateTabLabel } from '../navigation';
import { useNow } from '../hooks/useNow';
import { decisionAt } from '../decisionLifecycle';

export type DecisionAction = 'BET' | 'CONSIDER' | 'SKIP';
export type DataConfidence = 'Strong Data' | 'Partial Data' | 'Limited Data';
export interface SourceFreshness {
  state?: 'fresh' | 'degraded' | 'unavailable' | 'unknown';
  source?: string;
  observed_at?: string;
  expires_at?: string;
  max_stale_at?: string;
  warning?: string;
}

export interface Decision {
  matchId?: string;
  winProbability?: number | null;
  drawProbability?: number | null;
  scenarioShare?: number | null;
  tiedScenarioShare?: number | null;
  modelSource?: string;
  action: DecisionAction;
  side: string;
  opponent?: string;
  teamA?: string;
  teamB?: string;
  matchup?: string;
  matchDate?: string;
  slateDate?: string;
  eventStatus?: string | { state?: string; short?: string; name?: string; long?: string; completed?: boolean } | null;
  dataFreshness?: SourceFreshness | null;
  confidenceMeasure?: string;
  confidence: number;
  reason: string;
  data: DataConfidence;
  support?: string;
  cta?: string;
  logo?: string;
  leagueLogo?: string;
  teamALogo?: string;
  teamBLogo?: string;
  market?: { bookmaker: string; updated_at: string; home_decimal?: number; away_decimal?: number; home_spread?: number; total?: number; data_freshness?: SourceFreshness } | null;
  sport?: 'soccer' | 'nba' | 'nfl';
  homeId?: number | string;
  awayId?: number | string;
  leagueId?: number | string;
  odds?: { implied_prob: number; decimal?: number; american?: string };
}

/* ── Data badge ─────────────────────────────────────────── */

const DATA_STYLES: Record<DataConfidence, { badge: string; dot: string }> = {
  'Strong Data': { badge: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/10', dot: 'bg-emerald-400' },
  'Partial Data':{ badge: 'text-amber-300   border-amber-400/25  bg-amber-400/10',    dot: 'bg-amber-400'  },
  'Limited Data':{ badge: 'text-rose-300    border-rose-400/20   bg-rose-400/10',     dot: 'bg-rose-400'   },
};

export function DataBadge({ label }: { label: DataConfidence }) {
  const s = DATA_STYLES[label];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-semibold tracking-wide ${s.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {label}
    </span>
  );
}

/* ── Action badge ──────────────────────────────────────── */

const ACTION_CLASS: Record<DecisionAction, string> = {
  BET:     'badge-bet',
  CONSIDER:'badge-consider',
  SKIP:    'badge-skip',
};

const ACTION_ACCENT: Record<DecisionAction, string> = {
  BET:     'card-accent-bet',
  CONSIDER:'card-accent-consider',
  SKIP:    'card-accent-skip',
};

/* ── Confidence arc ────────────────────────────────────── */

function ConfidenceArc({ value, label = 'rule confidence' }: { value: number; action: DecisionAction; label?: string }) {
  const valid = Number.isFinite(value) && value >= 0 && value <= 100;
  return <div className="metric-value" role="img" aria-label={valid ? `${value}% ${label}` : `${label} unavailable`}>
    <strong>{valid ? `${value}%` : '—'}</strong>
  </div>;
}

/* ── Match date chip ───────────────────────────────────── */

function MatchDateChip({ date }: { date: string }) {
  if (!date) return null;
  const parsed = new Date(date);
  if (isNaN(parsed.getTime())) return null;
  const label = `${calendarFormat(parsed, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET`;
  return <span className="inline-flex rounded-full px-2 py-0.5 text-[10px] font-semibold border text-slate-400 border-white/10">{label}</span>;
}

/* ── Decision card ─────────────────────────────────────── */

export function DecisionCard({
  decision: rawDecision,
  featured = false,
  onAnalyze,
}: {
  decision: Decision;
  featured?: boolean;
  onAnalyze?: (d: Decision) => void;
}) {
  const now = useNow();
  const decision = decisionAt(rawDecision, now);
  const selectedSide = decision.side.replace(/ Win!?$/i, '');
  const home = decision.teamA || decision.side;
  const away = decision.teamB || decision.opponent || 'Away team';
  const competition = (decision.support || '').split(' | ')[0] || decision.sport?.toUpperCase() || 'Match analysis';
  return <article className={`card decision-card depth-card ${ACTION_ACCENT[decision.action]} ${featured && decision.action === 'BET' ? 'decision-card-featured' : ''}`}>
    <div className="match-card-top"><span className="competition-label"><span className="sport-dot" />{competition}</span>
      <span className={`action-badge ${ACTION_CLASS[decision.action]}`}>{decision.action}</span>
    </div>
    <div className="match-card-body">
      <div className="match-teams">
        <TeamIdentity name={home} logo={decision.teamALogo || (selectedSide === home ? decision.logo : '')} side="Home" />
        <TeamIdentity name={away} logo={decision.teamBLogo || (selectedSide === away ? decision.logo : '')} side="Away" />
      </div>
      <div className="match-metric">
        {decision.side === 'Unavailable' ? <span className="quiet-label">Unavailable</span> : <ConfidenceArc value={decision.confidence} action={decision.action} label={decision.sport === 'nfl' ? 'scenario share' : 'rule confidence'} />}
        <span>{decision.sport === 'nfl' ? 'Scenario share' : 'Rule confidence'}</span>
      </div>
    </div>
    {decision.dataFreshness?.warning && <p className="freshness-note" role="status">{decision.dataFreshness.warning}</p>}
    <div className="match-lean"><span>{decision.sport === 'nfl' ? 'Scenario lean' : 'Model lean'}</span><h2>{selectedSide}</h2><DataBadge label={decision.data} /></div>
    <p className="match-reason">{decision.reason}</p>
    {decision.sport !== 'nfl' && decision.side !== 'Unavailable' && decision.winProbability != null && <p className="match-market">Outcome probability: {decision.winProbability.toFixed(1)}% <span>· Separate from rule confidence</span></p>}
    {decision.market && <p className="match-market">Moneyline {decision.market.home_decimal?.toFixed(2)} / {decision.market.away_decimal?.toFixed(2)} <span>· {decision.market.bookmaker}</span></p>}
    <div className="match-card-footer">
      {decision.matchDate ? <MatchDateChip date={decision.matchDate} /> : <span className="kickoff-pending">Kickoff to be confirmed</span>}
      {onAnalyze && <button type="button" onClick={() => onAnalyze(decision)} className="btn-analyze">Analyze Matchup <ArrowUpRight size={15} /></button>}
    </div>
  </article>;
}

export function TeamIdentity({ name, logo, side }: { name: string; logo?: string; side: string }) {
  const initials = name.split(/\s+/).slice(0, 2).map(word => word[0]).join('');
  return <div className="team-identity"><span className="team-avatar" aria-hidden="true">{initials}
    {logo && <img src={logo} alt="" onError={event => { event.currentTarget.style.display = 'none'; }} />}
  </span><span className="team-name" title={name}>{name}</span><span className="team-side">{side}</span></div>;
}

/* ── Plan strip ─────────────────────────────────────────── */

export function PlanStrip({ bet, consider, skip, loading = false }: { bet: number; consider: number; skip: number; loading?: boolean }) {
  return (
    <section className="plan-strip" aria-label="Slate overview">
      <div className="plan-stat plan-stat-total"><span className="plan-icon"><Layers3 size={17} /></span><div><span className="plan-stat-label">ON THE SLATE</span><span className="plan-stat-num">{loading ? '—' : bet + consider + skip}<small>matchups</small></span></div></div>
      <div className="plan-stat">
        <span className="plan-icon plan-bet"><Target size={17} /></span><div><span className="plan-stat-label">BET</span><span className="plan-stat-num">{loading ? '—' : bet}<small>Meets decision rules</small></span></div>
      </div>
      <div className="plan-stat">
        <span className="plan-icon plan-consider"><Eye size={17} /></span><div><span className="plan-stat-label">CONSIDER</span><span className="plan-stat-num">{loading ? '—' : consider}<small>Take a closer look</small></span></div>
      </div>
      <div className="plan-stat">
        <span className="plan-icon"><Pause size={17} /></span><div><span className="plan-stat-label">SKIP</span><span className="plan-stat-num">{loading ? '—' : skip}<small>Outside current rules</small></span></div>
      </div>
    </section>
  );
}

/* ── Date tabs ──────────────────────────────────────────── */

export function DateTabs({
  dates,
  selected,
  onSelect,
}: {
  dates: string[];
  selected: string;
  onSelect: (d: string) => void;
}) {
  const now = useNow();
  if (!dates.length) return null;
  return (
    <div className="league-scroll">
      {dates.map((d) => (
        <button
          key={d}
          type="button"
          onClick={() => onSelect(d)}
          aria-pressed={selected === d}
          className={`league-pill ${selected === d ? 'league-pill-active' : ''}`}
        >
          {dateTabLabel(d, now)}
        </button>
      ))}
    </div>
  );
}

/* ── Empty state ────────────────────────────────────────── */

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">—</div>
      <p className="font-oswald text-base uppercase tracking-wider text-slate-300 mt-2">{title}</p>
      <p className="mt-1.5 text-sm text-slate-500">{body}</p>
    </div>
  );
}

/* ── Card skeleton ──────────────────────────────────────── */

export function CardSkeleton() {
  return (
    <div className="card space-y-4" role="status" aria-label="Loading matchup">
      <div className="flex items-center justify-between">
        <div className="skeleton-line h-2.5 w-1/3" />
        <div className="skeleton-line h-5 w-14 rounded-full" />
      </div>
      <div className="flex gap-3">
        <div className="skeleton-line h-12 w-12 rounded-xl shrink-0" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="skeleton-line h-4 w-2/3" />
          <div className="skeleton-line h-3 w-1/3" />
        </div>
        <div className="skeleton-line h-14 w-14 rounded-full shrink-0" />
      </div>
      <div className="skeleton-line h-[3px] w-full rounded-full" />
      <div className="space-y-2">
        <div className="skeleton-line h-3 w-full" />
        <div className="skeleton-line h-3 w-5/6" />
      </div>
      <div className="skeleton-line h-10 w-full rounded-lg" />
    </div>
  );
}
