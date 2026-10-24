import { useFetch } from '../hooks/useFetch';
import { useNow } from '../hooks/useNow';
import { calendarDate } from '../navigation';
import RequestError from './RequestError';
import type { Decision } from './DecisionCard';
import { pregameFailure } from '../decisionLifecycle';
import PropPicks, { type PropPick, type SportsbookStatus } from './PropPicks';

export default function SoccerProps({ decision }: { decision: Decision }) {
  const now = useNow();
  const parentFailure = pregameFailure(decision.matchDate, decision.eventStatus, decision.dataFreshness, now);
  const params = new URLSearchParams();
  if (decision.leagueId) params.set('league_id', String(decision.leagueId));
  if (decision.slateDate || decision.matchDate) params.set('date', decision.slateDate || calendarDate(decision.matchDate!));
  const { data, loading, error, retry, status } = useFetch<{ result: { picks: PropPick[]; sportsbook?: SportsbookStatus } }>(decision.matchId && !parentFailure
    ? `/api/soccer/matches/${encodeURIComponent(decision.matchId)}/props?${params}` : null);
  return <PropPicks title="Player props" received={!parentFailure && Boolean(data)} onRetry={retry} loading={!parentFailure && loading}
    unavailable={parentFailure || (error && status === 422 ? error : null)}
    error={!parentFailure && error && status !== 422 ? <RequestError message={error} onRetry={retry} /> : null}
    picks={data?.result?.picks} sportsbook={data?.result?.sportsbook} about={<>
      <p>The five props where the model most disagrees with each likely starter’s recent matches: shots, shots on target, goals, assists and fouls from ESPN box scores this season and last, plus tackles in the Premier League from Fantasy Premier League data.</p>
      <p>Fresh sportsbook targets and prices are matched automatically for supported markets and competitions. Other targets use recent-start medians. Premier League picks skip players listed injured or doubtful; other leagues have no injury feed here. Model accuracy against sportsbook lines is not established.</p>
    </>} />;
}
