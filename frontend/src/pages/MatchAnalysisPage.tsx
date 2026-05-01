import { DataBadge, DecisionCard, EmptyState, type Decision, type DataConfidence } from '../components/DecisionCard';
import ScorelinePredictor from '../components/ScorelinePredictor';

type ActionColor = { stroke: string; glow: string };
const ACTION_COLORS: Record<string, ActionColor> = {
  BET:     { stroke: '#34d399', glow: 'rgba(52,211,153,0.30)' },
  CONSIDER:{ stroke: '#fbbf24', glow: 'rgba(251,191,36,0.25)' },
  SKIP:    { stroke: '#64748b', glow: 'rgba(100,116,139,0.15)' },
};

function ProbabilityRing({ value, action }: { value: number; action: string }) {
  const r = 54;
  const circ = 2 * Math.PI * r;
  const filled = (value / 100) * circ;
  const { stroke, glow } = ACTION_COLORS[action] ?? ACTION_COLORS.SKIP;

  return (
    <div className="flex flex-col items-center gap-2">
      <svg width="136" height="136" viewBox="0 0 136 136" aria-label={`${value}% confidence`}>
        {/* Track */}
        <circle cx="68" cy="68" r={r} fill="none" stroke="rgba(255,255,255,0.05)" strokeWidth="10" />
        {/* Filled arc */}
        <circle
          cx="68" cy="68" r={r}
          fill="none"
          stroke={stroke}
          strokeWidth="10"
          strokeLinecap="round"
          strokeDasharray={`${filled} ${circ}`}
          strokeDashoffset={circ / 4}
          style={{ filter: `drop-shadow(0 0 6px ${glow})` }}
        />
        {/* Center text */}
        <text x="68" y="62" textAnchor="middle" fill="#fff" fontSize="24" fontWeight="700" fontFamily="Oswald,sans-serif">{value}%</text>
        <text x="68" y="80" textAnchor="middle" fill="#64748b" fontSize="11" fontFamily="Inter,sans-serif" letterSpacing="2">CONFIDENCE</text>
      </svg>
    </div>
  );
}

function TrustRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="trust-stat">
      <span className="trust-stat-label">{label}</span>
      <span className="trust-stat-value">{value}</span>
    </div>
  );
}

function AnalysisDetail({ decision }: { decision: Decision }) {
  const [competition, venue] = (decision.support || '').split(' | ');
  const dataLabel = decision.data as DataConfidence;

  const trustNote =
    decision.data === 'Strong Data'
      ? 'Form, venue context, and side-level data all agree.'
      : decision.data === 'Partial Data'
      ? 'Enough signal to act — confirm lineup news first.'
      : 'Thin data. Treat with extra caution.';

  const reasonLines = (decision.reason || 'No analysis available.')
    .split(' | ')
    .filter(Boolean);

  return (
    <div className="analysis-layout">
      {/* Left column */}
      <div className="section">
        <DecisionCard decision={decision} featured />

        <section className="card">
          <div className="section-header mb-4">
            <p className="section-label">Why This Pick</p>
            <div className="section-divider" />
          </div>
          <ul className="why-list">
            {reasonLines.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>
      </div>

      {/* Right sidebar */}
      <aside className="section">
        <div className="card flex flex-col items-center gap-5">
          <ProbabilityRing value={decision.confidence} action={decision.action} />
          <DataBadge label={dataLabel} />
          <p className="text-center text-[13px] text-slate-500 leading-relaxed">{trustNote}</p>
        </div>

        <div className="card">
          <div className="section-header mb-3">
            <p className="section-label">Match Context</p>
            <div className="section-divider" />
          </div>
          <TrustRow label="Competition" value={competition || 'Unknown'} />
          <TrustRow label="Venue" value={venue || 'TBD'} />
          <TrustRow
            label="Draw risk"
            value={decision.confidence >= 66 ? 'Low' : decision.confidence >= 55 ? 'Moderate' : 'High'}
          />
          <TrustRow label="Data tier" value={decision.data} />
        </div>
      </aside>
    </div>
  );
}

export default function MatchAnalysisPage({
  decision,
  sport = 'soccer',
  teamAId,
  teamBId,
  leagueId,
}: {
  decision: Decision | null;
  sport?: 'soccer' | 'nba';
  teamAId?: number | string;
  teamBId?: number | string;
  leagueId?: number | string;
}) {
  const matchup = decision?.matchup || 'Match Analysis';
  const competition = (decision?.support || '').split(' | ')[0] || (sport === 'nba' ? 'NBA' : 'Soccer');

  // Parse team names from matchup string "Team A vs Team B"
  const [teamAName, teamBName] = (() => {
    const parts = (decision?.matchup || '').split(' vs ');
    return parts.length === 2
      ? [parts[0].trim(), parts[1].trim()]
      : [decision?.side || 'Home', 'Away'];
  })();

  return (
    <div className="page-stack">
      <section className="hero-card">
        <p className="page-eyebrow">{competition}</p>
        <h1 className="page-title">{matchup}</h1>
        <p className="mt-3 max-w-xl text-slate-400 text-sm leading-relaxed">
          Full breakdown — decision first, evidence below.
        </p>
      </section>

      {decision ? (
        <>
          <AnalysisDetail decision={decision} />
          <ScorelinePredictor
            sport={sport}
            teamAName={teamAName}
            teamBName={teamBName}
            teamAId={teamAId}
            teamBId={teamBId}
            leagueId={leagueId}
          />
        </>
      ) : (
        <EmptyState title="No match selected" body="Go to Soccer or NBA and click Analyze Match on any card." />
      )}
    </div>
  );
}
