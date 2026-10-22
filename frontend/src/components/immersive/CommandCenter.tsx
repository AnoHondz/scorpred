import { ArrowRight, ArrowUpRight, CircleDot, Orbit } from 'lucide-react';
import type { CSSProperties, ReactNode, PointerEvent } from 'react';
import { calendarFormat, navigate } from '../../navigation';
import { decisionAt } from '../../decisionLifecycle';
import { useNow } from '../../hooks/useNow';
import type { Decision } from '../DecisionCard';
import SportsArena, { type ArenaSport } from './SportsArena';

const SPORT_LABELS = { nfl: 'NFL', nba: 'NBA', soccer: 'Soccer' };

export function DepthSurface({ children, className = '' }: { children: ReactNode; className?: string }) {
  function move(event: PointerEvent<HTMLElement>) {
    if (!matchMedia('(pointer:fine)').matches || matchMedia('(prefers-reduced-motion:reduce)').matches) return;
    const rect = event.currentTarget.getBoundingClientRect();
    event.currentTarget.style.setProperty('--tilt-x', `${((event.clientY - rect.top) / rect.height - .5) * -3}deg`);
    event.currentTarget.style.setProperty('--tilt-y', `${((event.clientX - rect.left) / rect.width - .5) * 3}deg`);
  }
  return <div className={`depth-surface ${className}`} onPointerMove={move} onPointerLeave={event => {
    event.currentTarget.style.setProperty('--tilt-x', '0deg'); event.currentTarget.style.setProperty('--tilt-y', '0deg');
  }}>{children}</div>;
}

export function SportPortals() {
  return <nav className="sport-portals" aria-label="Explore sports">{(['nfl', 'nba', 'soccer'] as const).map(sport =>
    <DepthSurface key={sport}><button className={`sport-portal portal-${sport}`} onClick={() => navigate(`/${sport}`)}>
      <span className={`portal-orb orb-${sport}`} aria-hidden="true" /><span><strong>{SPORT_LABELS[sport]}</strong><small>{sport === 'nba' ? 'Courtside context & matchups' : sport === 'nfl' ? 'The week ahead, in focus' : 'Fixtures, form & perspective'}</small></span><ArrowRight size={18} />
    </button></DepthSurface>)}</nav>;
}

export function AnimatedIndicator({ label, value, share, tone = 'emerald' }: { label: string; value: string | number; share?: number; tone?: string }) {
  return <div className={`animated-indicator indicator-${tone}`} data-unavailable={value === 'Unavailable'}><span>{label}</span><strong>{value}</strong>
    {share != null && Number.isFinite(share) && <div className="indicator-track"><span style={{ '--share': Math.max(0, Math.min(1, share)) } as CSSProperties} /></div>}
  </div>;
}

export function MatchupStage({ sport, decision: raw, onSelect, label = 'FEATURED MATCHUP' }: {
  sport: ArenaSport; decision?: Decision | null; onSelect?: (decision: Decision) => void; label?: string;
}) {
  const now = useNow();
  const decision = raw ? decisionAt(raw, now) : null;
  const measure = sport === 'nfl' ? decision?.scenarioShare : decision?.winProbability;
  const observed = decision?.dataFreshness?.observed_at;
  return <section className={`matchup-stage stage-${sport}`} aria-label={`${SPORT_LABELS[sport]} matchup arena`}>
    <div className="stage-heading"><span><i className="signal-dot" />{SPORT_LABELS[sport]} <span> / </span>{label}</span>
      <span>{decision?.matchDate ? `${calendarFormat(decision.matchDate, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET` : 'Schedule & availability'}</span></div>
    <div className="stage-scene"><SportsArena sport={sport} />
      {decision && <div className="floating-matchup"><div className="floating-team floating-home">{decision.teamALogo && <img src={decision.teamALogo} alt="" />}<small>HOME</small><h2>{decision.teamA}</h2></div>
        <span className="stage-versus">VS</span><div className="floating-team floating-away">{decision.teamBLogo && <img src={decision.teamBLogo} alt="" />}<small>AWAY</small><h2>{decision.teamB}</h2></div></div>}
    </div>
    <div className="stage-bottom"><div className="stage-summary"><Orbit size={18} /><div><strong>{decision ? decision.side === 'Unavailable' ? 'The matchup, beyond a prediction.' : decision.side : 'Every matchup has a story.'}</strong>
      <p>{decision?.reason || 'Explore available schedules. Estimates appear only when the required source data supports them.'}</p></div></div>
      {decision && <AnimatedIndicator label={sport === 'nfl' ? 'Experimental scenario share' : 'Outcome probability'} value={measure == null || decision.side === 'Unavailable' ? 'Unavailable' : `${measure.toFixed(1)}%`} share={measure == null ? undefined : measure / 100} tone={sport === 'nfl' ? 'blue' : 'emerald'} />}
      {decision && onSelect && <button className="stage-action" onClick={() => onSelect(decision)}>Explore matchup<ArrowUpRight size={17} /></button>}
    </div>
    <p className="stage-source"><CircleDot size={11} />{observed ? `Source observed ${calendarFormat(observed, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET` : 'Source observation time unavailable'}<span>{sport === 'nfl' ? 'Descriptive scenarios · not calibrated win probabilities' : 'Probabilities & confidence retain their existing method'}</span></p>
  </section>;
}

export function CoverageVisual({ groups }: { groups: { name: string; count: number; loading: boolean }[] }) {
  const total = groups.reduce((sum, group) => sum + group.count, 0);
  const complete = groups.every(group => !group.loading);
  return <section className="coverage-visual card" aria-label="Schedule coverage visualization"><div><p className="page-eyebrow">SIGNAL OVERVIEW</p><h2 className="section-title">The available slate.</h2><p className="quiet-label">Observed matchups by sport. Counts are not confidence ratings.</p></div>
    <div className="coverage-columns">{groups.map(group => <AnimatedIndicator key={group.name} label={group.name} value={group.loading ? '…' : group.count} share={complete && total ? group.count / total : undefined} tone={group.name === 'NFL' ? 'blue' : group.name === 'NBA' ? 'purple' : 'emerald'} />)}</div>
  </section>;
}
