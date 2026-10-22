import { useEffect, useState } from 'react';
import { useFetch } from '../hooks/useFetch';
import type { Decision, SourceFreshness } from './DecisionCard';
import { calendarDate, calendarFormat } from '../navigation';
import { AnimatedIndicator } from './immersive/CommandCenter';
import NBAEarlySeasonResearch from './NBAEarlySeasonResearch';

interface Summary {
  games: number; wins: number; losses: number; points_for: number | null; points_against: number | null;
  scope: string; recent_results: { game_id: string; date: string; opponent: string; result: string;
    points_for: number; points_against: number; home: boolean }[];
}
interface TeamContext {
  team: { id: string; name: string }; current: Summary; previous: Summary;
  current_season: number; previous_season: number; current_status: string; current_source: SourceFreshness;
  historical_source: { files: string[]; historical_pregame_availability: string };
}
interface Context {
  version: string; role: string; refresh_pending: boolean; statistics_cutoff: string; notice: string;
  teams: { home: TeamContext; away: TeamContext };
  game: { result?: { home: { points: number }; visitors: { points: number } } | null };
}

export default function NBAContext({ decision, compact = false }: { decision: Decision; compact?: boolean }) {
  const day = decision.slateDate || (decision.matchDate ? calendarDate(decision.matchDate) : '');
  const { data, loading, error, retry } = useFetch<{ result: Context }>(decision.matchId
    ? `/api/nba/matches/${encodeURIComponent(decision.matchId)}/context?date=${day}` : null);
  const [period, setPeriod] = useState<'current' | 'previous'>('previous');
  const result = data?.result;
  useEffect(() => {
    if (!result?.refresh_pending) return;
    const timeout = setTimeout(retry, 2000);
    return () => clearTimeout(timeout);
  }, [result, retry]);
  if (loading) return <section className="card" aria-label="NBA team comparisons"><p role="status">Loading available team comparisons…</p></section>;
  if (error) return <section className="card" aria-label="NBA team comparisons"><p className="coverage-note" role="status">Team comparisons unavailable: {error}</p><button className="text-button" onClick={retry}>Retry comparisons</button></section>;
  if (!result) return null;
  const teams = [result.teams.home, result.teams.away];
  return <section className="section nba-context" aria-label="NBA team comparisons">
    <div className="section-heading-row"><div><p className="page-eyebrow">NBA MATCHUP INTELLIGENCE</p><h2 className="section-title">The evidence beyond a prediction.</h2></div><span className="research-badge">Descriptive · no probability fallback</span></div>
    <p className="coverage-note">Observed team statistics are separate from prediction availability. A missing prediction does not mean team history is missing.</p>
    <div className="sport-filter" aria-label="NBA comparison period">
      <button aria-pressed={period === 'current'} onClick={() => setPeriod('current')}>Current season</button>
      <button aria-pressed={period === 'previous'} onClick={() => setPeriod('previous')}>Previous season</button>
    </div>
    <div className="grid-2">{teams.map(team => {
      const summary = team[period];
      const season = period === 'current' ? team.current_season : team.previous_season;
      return <article className="card" key={team.team.id}>
        <p className="page-eyebrow">{season - 1}–{String(season).slice(-2)} · {period === 'current' ? 'Current observations' : 'Existing local archive'}</p>
        <h3 className="panel-title">{team.team.name}</h3>
        {period === 'current' && <p className="quiet-label">{team.current_status === 'refreshing' ? 'Source refresh in progress; historical context remains available.' : team.current_status === 'unavailable' ? 'Current source unavailable. Zero displayed observations do not establish a 0–0 season record.' : `Source: ${team.current_status}`}</p>}
        <div className="context-metrics">
          <div><span>Observed record</span><strong>{summary.games ? `${summary.wins}–${summary.losses}` : 'Unavailable'}</strong></div>
          <div><span>Games in sample</span><strong>{summary.games}</strong></div>
          <div><span>Points / game</span><strong>{summary.points_for?.toFixed(1) ?? 'Unavailable'}</strong></div>
          <div><span>Conceded / game</span><strong>{summary.points_against?.toFixed(1) ?? 'Unavailable'}</strong></div>
        </div>
        <p className="quiet-label">{summary.scope}. Coverage may be incomplete; no possession-based efficiency is implied.</p>
        {!compact && <div className="context-scoring-bar"><AnimatedIndicator label="Observed scoring comparison" value={summary.points_for == null ? 'Unavailable' : `${summary.points_for.toFixed(1)} points / game`}
          share={summary.points_for != null ? summary.points_for / Math.max(1, ...teams.map(value => value[period].points_for || 0)) : undefined} tone={team === teams[0] ? 'emerald' : 'blue'} /></div>
        }
        {!compact && (summary.recent_results.length ? <div className="table-scroll"><table className="evaluation-table"><caption>Recent results in this sample</caption>
          <thead><tr><th>Date</th><th>Opponent</th><th>Result</th><th>Score</th></tr></thead><tbody>{summary.recent_results.map(row => <tr key={row.game_id}>
            <td>{calendarFormat(row.date, { month: 'short', day: 'numeric' })}</td><td>{row.opponent} · {row.home ? 'H' : 'A'}</td><td>{row.result}</td><td>{row.points_for}–{row.points_against}</td>
        </tr>)}</tbody></table></div> : <p className="coverage-note">No eligible completed games in the available sample.</p>)}
        {period === 'current' && <p className="quiet-label">Source observed: {team.current_source?.observed_at ? `${calendarFormat(team.current_source.observed_at, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET` : 'Unverified'}. State: {team.current_source?.state || 'Unavailable'}.</p>}
        {period === 'previous' && <p className="quiet-label">{team.historical_source.files.length} existing archive files · original receipt time unverified.</p>}
      </article>;
    })}</div>
    {result.game.result && <p className="coverage-note">Recorded final score: {decision.teamA} {result.game.result.home.points} – {result.game.result.visitors.points} {decision.teamB}. This is an observed result, not a prediction.</p>}
    <NBAEarlySeasonResearch key={decision.matchId} decision={decision} />
    <details className="card"><summary>Availability, sources & prediction policy</summary><p className="quiet-label">{result.notice}</p>
      <p className="quiet-label">Statistics cutoff: {result.statistics_cutoff}. Version: {result.version}.</p>
      <p className="quiet-label">Existing winner rules need two current-season observations; scoring needs three. No validated prior-season probability substitution is available. Historical records are kept separate from model inputs.</p>
    </details>
  </section>;
}
