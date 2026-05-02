export type DecisionAction = 'BET' | 'CONSIDER' | 'SKIP';
export type DataConfidence = 'Strong Data' | 'Partial Data' | 'Limited Data';

export interface Decision {
  action: DecisionAction;
  side: string;
  opponent?: string;
  teamA?: string;
  teamB?: string;
  matchup?: string;
  matchDate?: string;
  confidence: number;
  reason: string;
  data: DataConfidence;
  support?: string;
  cta?: string;
  logo?: string;
  leagueLogo?: string;
  sport?: 'soccer' | 'nba';
  homeId?: number | string;
  awayId?: number | string;
  leagueId?: number | string;
}

const ACTION_BADGE: Record<DecisionAction, string> = {
  BET:     'text-emerald-900 bg-emerald-400 border-emerald-400',
  CONSIDER:'text-amber-900   bg-amber-400   border-amber-400',
  SKIP:    'text-slate-300   bg-slate-700   border-slate-600',
};

const BAR_COLOR: Record<DecisionAction, string> = {
  BET:     'bg-emerald-400',
  CONSIDER:'bg-amber-400',
  SKIP:    'bg-slate-500',
};

const DATA_STYLES: Record<DataConfidence, { badge: string; dot: string }> = {
  'Strong Data': { badge: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/10', dot: 'bg-emerald-400' },
  'Partial Data':{ badge: 'text-amber-300   border-amber-400/25  bg-amber-400/10',   dot: 'bg-amber-400'  },
  'Limited Data':{ badge: 'text-rose-300    border-rose-400/20   bg-rose-400/10',    dot: 'bg-rose-400'   },
};

const ACTION_ACCENT: Record<DecisionAction, string> = {
  BET:     'card-accent-bet',
  CONSIDER:'card-accent-consider',
  SKIP:    'card-accent-skip',
};

export function DataBadge({ label }: { label: DataConfidence }) {
  const s = DATA_STYLES[label];
  return (
    <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[11px] font-semibold tracking-wide ${s.badge}`}>
      <span className={`h-1.5 w-1.5 rounded-full ${s.dot}`} />
      {label}
    </span>
  );
}

function ConfidenceArc({ value, action }: { value: number; action: DecisionAction }) {
  const r = 22;
  const circ = 2 * Math.PI * r;
  const filled = (value / 100) * circ;
  const colors: Record<DecisionAction, string> = {
    BET: '#34d399',
    CONSIDER: '#fbbf24',
    SKIP: '#64748b',
  };
  const col = colors[action];
  return (
    <svg width="58" height="58" viewBox="0 0 60 60" className="shrink-0" aria-hidden="true">
      <circle cx="30" cy="30" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="5" />
      <circle
        cx="30" cy="30" r={r}
        fill="none"
        stroke={col}
        strokeWidth="5"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circ}`}
        strokeDashoffset={circ / 4}
      />
      <text x="30" y="34" textAnchor="middle" fill="#fff" fontSize="11" fontWeight="700" fontFamily="Oswald,sans-serif">
        {value}%
      </text>
    </svg>
  );
}

function MatchDateChip({ date }: { date: string }) {
  if (!date) return null;
  try {
    const d = new Date(date);
    if (isNaN(d.getTime())) return null;
    const now = new Date();
    const diffMs = d.getTime() - now.getTime();
    const diffH = diffMs / 3_600_000;
    let label: string;
    if (diffH < 0) label = 'Completed';
    else if (diffH < 1) label = `${Math.round(diffH * 60)}m`;
    else if (diffH < 24) label = `${Math.floor(diffH)}h`;
    else label = d.toLocaleDateString([], { month: 'short', day: 'numeric' });
    const isLive = diffH >= -2 && diffH <= 0;
    return (
      <span className={`inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-semibold border
        ${isLive ? 'text-rose-300 border-rose-400/30 bg-rose-400/10' : 'text-slate-500 border-white/[0.07] bg-white/[0.03]'}`}>
        {isLive && <span className="h-1.5 w-1.5 rounded-full bg-rose-400 animate-pulse" />}
        {label}
      </span>
    );
  } catch {
    return null;
  }
}

export function DecisionCard({
  decision,
  featured = false,
  onAnalyze,
}: {
  decision: Decision;
  featured?: boolean;
  onAnalyze?: (d: Decision) => void;
}) {
  const initials = decision.side
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'TM';

  const opponent = decision.opponent || decision.teamB || '';
  const accentClass = ACTION_ACCENT[decision.action];

  return (
    <article className={`card decision-card ${accentClass} ${featured ? 'decision-card-featured' : ''}`}>
      {/* Row 1: matchup label + date chip + action badge */}
      <div className="flex items-start justify-between gap-2 mb-4">
        <div className="flex items-center gap-2 min-w-0">
          {decision.leagueLogo && (
            <img
              src={decision.leagueLogo}
              alt=""
              className="h-4 w-4 rounded border border-white/[0.08] bg-white/90 object-contain p-px shrink-0"
              onError={(e) => { e.currentTarget.style.display = 'none'; }}
            />
          )}
          <p className="text-[11px] uppercase tracking-[0.14em] text-slate-500 leading-tight truncate">
            {decision.matchup || 'Matchup'}
          </p>
        </div>
        <div className="flex items-center gap-1.5 shrink-0">
          {decision.matchDate && <MatchDateChip date={decision.matchDate} />}
          <span className={`rounded-full border px-2.5 py-0.5 text-[10px] font-black tracking-widest ${ACTION_BADGE[decision.action]}`}>
            {decision.action}
          </span>
        </div>
      </div>

      {/* Row 2: logo + team name + confidence arc */}
      <div className="flex items-center gap-3 mb-4">
        {decision.logo ? (
          <img
            src={decision.logo}
            alt={`${decision.side} logo`}
            className="h-11 w-11 rounded-xl border border-white/[0.10] bg-white object-contain p-1 shadow-md shrink-0"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
        ) : (
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.04] font-oswald text-sm text-slate-300">
            {initials}
          </span>
        )}
        <div className="min-w-0 flex-1">
          <h2 className="font-oswald text-xl uppercase tracking-wide text-white leading-tight truncate">
            {decision.side.replace(/ Win!?$/i, '')}
          </h2>
          {opponent && (
            <p className="text-[11px] text-slate-500 mt-0.5 truncate">vs {opponent}</p>
          )}
          <div className="mt-1">
            <DataBadge label={decision.data} />
          </div>
        </div>
        <div className="shrink-0">
          <ConfidenceArc value={decision.confidence} action={decision.action} />
        </div>
      </div>

      {/* Row 3: confidence bar */}
      <div className="mb-4">
        <div className="h-1 overflow-hidden rounded-full bg-white/[0.06]">
          <div
            className={`h-full rounded-full transition-all duration-700 ${BAR_COLOR[decision.action]}`}
            style={{ width: `${decision.confidence}%` }}
          />
        </div>
      </div>

      {/* Row 4: reason */}
      <p className="text-[13px] leading-relaxed text-slate-400 line-clamp-3">{decision.reason}</p>

      {/* Row 5: support */}
      {decision.support && (
        <p className="mt-2.5 text-[11px] text-slate-600 leading-snug border-t border-white/[0.05] pt-2.5">
          {decision.support}
        </p>
      )}

      {/* Analyze button */}
      {onAnalyze && (
        <button
          type="button"
          onClick={() => onAnalyze(decision)}
          className="mt-4 w-full rounded-lg border border-teal-500/25 bg-teal-500/[0.07] px-4 py-2.5 text-[12px] font-bold uppercase tracking-[0.10em] text-teal-400 transition hover:border-teal-400/50 hover:bg-teal-500/[0.14] hover:text-teal-200 active:scale-[0.98]"
        >
          Analyze Match →
        </button>
      )}

      {decision.cta && (
        <button
          type="button"
          className="mt-3 w-full rounded-lg border border-white/[0.07] px-4 py-2 text-sm text-slate-400 transition hover:border-emerald-400/25 hover:text-emerald-300 hover:bg-emerald-400/5"
        >
          {decision.cta}
        </button>
      )}
    </article>
  );
}

export function PlanStrip({ bet, consider, skip }: { bet: number; consider: number; skip: number }) {
  return (
    <section className="plan-strip">
      <div className="plan-stat">
        <span className="plan-stat-num" style={{ color: '#34d399' }}>{bet}</span>
        <span className="plan-stat-label">BET</span>
      </div>
      <div className="plan-divider" />
      <div className="plan-stat">
        <span className="plan-stat-num" style={{ color: '#fbbf24' }}>{consider}</span>
        <span className="plan-stat-label">CONSIDER</span>
      </div>
      <div className="plan-divider" />
      <div className="plan-stat">
        <span className="plan-stat-num" style={{ color: '#64748b' }}>{skip}</span>
        <span className="plan-stat-label">SKIP</span>
      </div>
    </section>
  );
}

export function DateTabs({
  dates,
  selected,
  onSelect,
}: {
  dates: string[];
  selected: string;
  onSelect: (d: string) => void;
}) {
  if (!dates.length) return null;
  const fmt = (iso: string) => {
    try {
      const d = new Date(iso + 'T00:00:00');
      const today = new Date();
      const tomorrow = new Date(today); tomorrow.setDate(today.getDate() + 1);
      if (iso === today.toISOString().slice(0, 10)) return 'Today';
      if (iso === tomorrow.toISOString().slice(0, 10)) return 'Tomorrow';
      return d.toLocaleDateString([], { weekday: 'short', month: 'short', day: 'numeric' });
    } catch { return iso; }
  };
  return (
    <div className="flex gap-2 overflow-x-auto pb-1 scrollbar-none">
      {dates.map((d) => (
        <button
          key={d}
          type="button"
          onClick={() => onSelect(d)}
          className={`flex-shrink-0 rounded-full border px-4 py-1.5 text-[12px] font-semibold transition
            ${selected === d
              ? 'border-teal-500/50 bg-teal-500/[0.12] text-teal-300'
              : 'border-white/[0.08] bg-white/[0.03] text-slate-500 hover:border-white/20 hover:text-slate-300'
            }`}
        >
          {fmt(d)}
        </button>
      ))}
    </div>
  );
}

export function EmptyState({ title, body }: { title: string; body: string }) {
  return (
    <div className="empty-state">
      <div className="empty-state-icon" aria-hidden="true">—</div>
      <p className="font-oswald text-base uppercase tracking-wider text-slate-300 mt-2">{title}</p>
      <p className="mt-1.5 text-sm text-slate-500">{body}</p>
    </div>
  );
}

export function CardSkeleton() {
  return (
    <div className="card animate-pulse space-y-4">
      <div className="flex items-center justify-between">
        <div className="h-2.5 w-1/3 rounded bg-white/[0.05]" />
        <div className="h-5 w-14 rounded-full bg-white/[0.05]" />
      </div>
      <div className="flex gap-3">
        <div className="h-11 w-11 rounded-xl bg-white/[0.05] shrink-0" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-4 w-2/3 rounded bg-white/[0.06]" />
          <div className="h-3 w-1/3 rounded bg-white/[0.04]" />
        </div>
        <div className="h-14 w-14 rounded-full bg-white/[0.04] shrink-0" />
      </div>
      <div className="h-1 w-full rounded-full bg-white/[0.05]" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-white/[0.04]" />
        <div className="h-3 w-5/6 rounded bg-white/[0.04]" />
      </div>
      <div className="h-9 w-full rounded-lg bg-white/[0.04]" />
    </div>
  );
}
