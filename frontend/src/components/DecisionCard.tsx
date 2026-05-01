export type DecisionAction = 'BET' | 'CONSIDER' | 'SKIP';
export type DataConfidence = 'Strong Data' | 'Partial Data' | 'Limited Data';

export interface Decision {
  action: DecisionAction;
  side: string;
  matchup?: string;
  confidence: number;
  reason: string;
  data: DataConfidence;
  support?: string;
  cta?: string;
  logo?: string;
  leagueLogo?: string;
  /** Extra metadata forwarded to ScorelinePredictor */
  sport?: 'soccer' | 'nba';
  homeId?: number | string;
  awayId?: number | string;
  leagueId?: number | string;
}

const ACTION_BADGE: Record<DecisionAction, string> = {
  BET:     'text-emerald-200 border-emerald-400/30 bg-emerald-400/12',
  CONSIDER:'text-amber-200  border-amber-400/30  bg-amber-400/12',
  SKIP:    'text-slate-400  border-slate-500/30  bg-slate-500/10',
};

const BAR_COLOR: Record<DecisionAction, string> = {
  BET:     'bg-emerald-400',
  CONSIDER:'bg-amber-400',
  SKIP:    'bg-slate-500',
};

const BAR_GLOW: Record<DecisionAction, string> = {
  BET:     'shadow-[0_0_12px_2px_rgba(52,211,153,0.35)]',
  CONSIDER:'shadow-[0_0_12px_2px_rgba(251,191,36,0.3)]',
  SKIP:    '',
};

const DATA_STYLES: Record<DataConfidence, { badge: string; dot: string }> = {
  'Strong Data': { badge: 'text-emerald-300 border-emerald-400/25 bg-emerald-400/10', dot: 'bg-emerald-400' },
  'Partial Data':{ badge: 'text-amber-300  border-amber-400/25  bg-amber-400/10',  dot: 'bg-amber-400'  },
  'Limited Data':{ badge: 'text-rose-300   border-rose-400/20   bg-rose-400/10',   dot: 'bg-rose-400'   },
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
  return (
    <svg width="60" height="60" viewBox="0 0 60 60" className="shrink-0" aria-hidden="true">
      <circle cx="30" cy="30" r={r} fill="none" stroke="rgba(255,255,255,0.06)" strokeWidth="4" />
      <circle
        cx="30" cy="30" r={r}
        fill="none"
        stroke={colors[action]}
        strokeWidth="4"
        strokeLinecap="round"
        strokeDasharray={`${filled} ${circ}`}
        strokeDashoffset={circ / 4}
        style={{ filter: `drop-shadow(0 0 4px ${colors[action]}88)` }}
      />
      <text x="30" y="35" textAnchor="middle" fill="#fff" fontSize="12" fontWeight="700" fontFamily="Oswald,sans-serif">
        {value}%
      </text>
    </svg>
  );
}

export function DecisionCard({ decision, featured = false, onAnalyze }: { decision: Decision; featured?: boolean; onAnalyze?: (d: Decision) => void }) {
  const initials = decision.side
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase())
    .join('') || 'TM';

  const accentClass = ACTION_ACCENT[decision.action];

  return (
    <article className={`card decision-card ${accentClass} ${featured ? 'decision-card-featured' : ''}`}>
      {/* Top row: matchup + badges */}
      <div className="flex items-start justify-between gap-3 mb-4">
        <p className="text-[11px] uppercase tracking-[0.16em] text-slate-500 leading-tight">
          {decision.matchup || 'Matchup'}
        </p>
        <div className="flex items-center gap-1.5 shrink-0">
          {decision.leagueLogo && (
            <img
              src={decision.leagueLogo}
              alt=""
              className="h-5 w-5 rounded border border-white/[0.08] bg-white/90 object-contain p-0.5"
              onError={(e) => { e.currentTarget.style.display = 'none'; }}
            />
          )}
          <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-bold tracking-widest ${ACTION_BADGE[decision.action]}`}>
            {decision.action}
          </span>
        </div>
      </div>

      {/* Side identity row */}
      <div className="flex items-center gap-3 mb-5">
        {decision.logo ? (
          <img
            src={decision.logo}
            alt={`${decision.side} logo`}
            className="h-11 w-11 rounded-xl border border-white/[0.1] bg-white object-contain p-1 shadow-md"
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
          />
        ) : (
          <span className="grid h-11 w-11 shrink-0 place-items-center rounded-xl border border-white/[0.08] bg-white/[0.04] font-oswald text-sm text-slate-300">
            {initials}
          </span>
        )}
        <div className="min-w-0">
          <h2 className="font-oswald text-2xl uppercase tracking-wide text-white leading-tight truncate">
            {decision.side}
          </h2>
          <DataBadge label={decision.data} />
        </div>
        <div className="ml-auto shrink-0">
          <ConfidenceArc value={decision.confidence} action={decision.action} />
        </div>
      </div>

      {/* Confidence bar */}
      <div className="mb-4">
          <div className="h-1.5 overflow-hidden rounded-full bg-white/[0.05]">
          <div
            className={`h-full rounded-full transition-all duration-700 ${BAR_COLOR[decision.action]} ${BAR_GLOW[decision.action]}`}
            style={{ width: `${decision.confidence}%` }}
          />
        </div>
      </div>

      {/* Reason */}
      <p className="text-[14px] leading-relaxed text-slate-300 line-clamp-3">{decision.reason}</p>

      {/* Support */}
      {decision.support && (
        <p className="mt-3 text-[12px] text-slate-500 leading-snug border-t border-white/[0.05] pt-3">
          {decision.support}
        </p>
      )}

      {onAnalyze && (
        <button
          type="button"
          onClick={() => onAnalyze(decision)}
          className="mt-4 w-full rounded-lg border border-emerald-400/25 bg-emerald-400/[0.07] px-4 py-2.5 text-[12px] font-semibold uppercase tracking-widest text-emerald-300 transition hover:border-emerald-400/50 hover:bg-emerald-400/[0.14] hover:text-emerald-200 active:scale-[0.98]"
        >
          Analyze Match →
        </button>
      )}

      {decision.cta && (
        <button
          type="button"
          className="mt-4 w-full rounded-lg border border-white/[0.08] px-4 py-2 text-sm text-slate-300 transition hover:border-emerald-400/30 hover:text-emerald-200 hover:bg-emerald-400/5"
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
      <div className="h-3 w-1/3 rounded bg-white/[0.06]" />
      <div className="flex gap-3">
        <div className="h-11 w-11 rounded-xl bg-white/[0.05]" />
        <div className="flex-1 space-y-2 pt-1">
          <div className="h-4 w-2/3 rounded bg-white/[0.06]" />
          <div className="h-3 w-1/3 rounded bg-white/[0.04]" />
        </div>
      </div>
      <div className="h-1.5 w-full rounded-full bg-white/[0.05]" />
      <div className="space-y-2">
        <div className="h-3 w-full rounded bg-white/[0.04]" />
        <div className="h-3 w-5/6 rounded bg-white/[0.04]" />
      </div>
    </div>
  );
}
