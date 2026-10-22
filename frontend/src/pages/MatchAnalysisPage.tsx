import { DataBadge, DecisionCard, EmptyState, TeamIdentity, type Decision } from '../components/DecisionCard';
import ScorelinePredictor from '../components/ScorelinePredictor';
import NFLAnalysis from '../components/NFLAnalysis';
import NFLWinnerResearch from '../components/NFLWinnerResearch';
import { decisionAt } from '../decisionLifecycle';
import { useNow } from '../hooks/useNow';
import { calendarFormat } from '../navigation';
import NBAContext from '../components/NBAContext';
import { MatchupStage } from '../components/immersive/CommandCenter';

function TrustRow({ label, value }: { label: string; value: string }) {
  return <div className="trust-stat"><span className="trust-stat-label">{label}</span><span className="trust-stat-value">{value}</span></div>;
}

function AnalysisDetail({ decision }: { decision: Decision }) {
  const nfl = decision.sport === 'nfl';
  const selectedShare = nfl ? decision.scenarioShare : decision.winProbability;
  const tiedShare = nfl ? decision.tiedScenarioShare : decision.drawProbability;
  const [competition, venue] = (decision.support || '').split(' | ');
  const reasonLines = (decision.reason || 'No analysis available.').split(' | ').filter(Boolean);
  const measureAvailable = decision.side !== 'Unavailable' && Number.isFinite(decision.confidence);
  return <div className="analysis-layout">
    <div className="section">
      <div className="section-heading-row"><h2 className="section-title">Game outlook</h2><span className="quiet-label">Current dashboard analysis</span></div>
      <DecisionCard decision={decision} featured />
      <details className="card" open><summary><h3 className="panel-title">Behind the decision</h3></summary>
        <ul className="why-list">{reasonLines.map(line => <li key={line}>{line}</li>)}</ul>
      </details>
    </div>
    <aside className="section" aria-label="Analysis context">
      <div className="card">
        <p className="section-label">{nfl ? 'Scenario share' : 'Rule confidence'}</p>
        <div className="analysis-measure" role="img" aria-label={measureAvailable ? `${decision.confidence}% ${nfl ? 'scenarios' : 'confidence'}` : `${nfl ? 'Scenario share' : 'Rule confidence'} unavailable`}>
          <strong>{measureAvailable ? `${decision.confidence}%` : 'Unavailable'}</strong>
          {measureAvailable && <div className="measure-track"><span style={{ width: `${decision.confidence}%` }} /></div>}
        </div>
        <div className="mt-4"><DataBadge label={decision.data} /></div>
        <p className="score-model-note">{nfl ? 'Descriptive scoring scenarios, not calibrated win probabilities.' : 'Rule confidence measures agreement within the weighted rules. It is distinct from win probability.'}</p>
      </div>
      <div className="card"><h3 className="panel-title">Match context</h3>
        <TrustRow label="Competition" value={competition || decision.sport?.toUpperCase() || 'Unavailable'} />
        <TrustRow label="Venue" value={venue || 'Unavailable'} />
        {decision.sport !== 'nba' && <TrustRow label={nfl ? 'Tied scenarios' : 'Draw probability'} value={tiedShare == null ? 'Unavailable' : `${tiedShare.toFixed(1)}%`} />}
        <TrustRow label={nfl ? 'Selected-side scenarios' : 'Win probability'} value={selectedShare == null ? 'Unavailable' : `${selectedShare.toFixed(1)}%`} />
        <TrustRow label="Analysis source" value={nfl ? 'Experimental scoring rules' : decision.modelSource === 'weighted_rules' ? 'Weighted rule model' : decision.modelSource || 'Unavailable'} />
        <TrustRow label="Data tier" value={decision.data} />
        {decision.dataFreshness?.observed_at && <TrustRow label="Source observed" value={`${calendarFormat(decision.dataFreshness.observed_at, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET`} />}
      </div>
    </aside>
  </div>;
}

export default function MatchAnalysisPage({ decision: rawDecision, sport = 'soccer', teamAId, teamBId, leagueId }: {
  decision: Decision | null;
  sport?: 'soccer' | 'nba' | 'nfl';
  teamAId?: number | string;
  teamBId?: number | string;
  leagueId?: number | string;
}) {
  const now = useNow();
  const decision = rawDecision ? decisionAt(rawDecision, now) : null;
  const matchup = decision?.matchup || 'Match Analysis';
  const [competition, venue] = (decision?.support || '').split(' | ');
  const teamAName = decision?.teamA || matchup.split(' vs ')[0] || 'Home';
  const teamBName = decision?.teamB || matchup.split(' vs ')[1] || 'Away';
  return <div className="page-stack">
    <section className="hero-card analysis-masthead">
      <div><p className="page-eyebrow">{competition || sport.toUpperCase()} · MATCH ANALYSIS</p>
        <h1 className="page-title">{matchup}</h1></div>
      {decision && <>
        <div className="analysis-teams"><TeamIdentity name={teamAName} logo={decision.teamALogo} side="Home" /><span className="analysis-vs">VS</span><TeamIdentity name={teamBName} logo={decision.teamBLogo} side="Away" /></div>
        <div className="match-metadata"><span>{decision.matchDate ? `${calendarFormat(decision.matchDate, { weekday: 'short', month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET` : 'Kickoff unavailable'}</span><span>{venue || 'Venue unavailable'}</span></div>
      </>}
    </section>
    {sport === 'nba' && decision && <NBAContext decision={decision} />}
    <MatchupStage sport={sport} decision={decision} label="MATCHUP EXPLORER" />
    {decision ? <>
      <AnalysisDetail decision={decision} />
      {sport === 'nfl' ? <><NFLAnalysis decision={decision} /><NFLWinnerResearch /></> : <ScorelinePredictor sport={sport} teamAName={teamAName} teamBName={teamBName} teamAId={teamAId} teamBId={teamBId} leagueId={leagueId} kickoff={decision.matchDate} matchId={decision.matchId} eventStatus={decision.eventStatus} dataFreshness={decision.dataFreshness} />}
    </> : <EmptyState title="No match selected" body="Go to Soccer, NBA or NFL and click Analyze Matchup on any card." />}
  </div>;
}
