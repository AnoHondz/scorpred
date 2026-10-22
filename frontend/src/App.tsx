import DashboardLayout from './components/DashboardTheme';
import HomePage from './pages/HomePage';
import { lazy, Suspense } from 'react';
import RequestError from './components/RequestError';
import { CardSkeleton, type Decision } from './components/DecisionCard';
import { useFetch } from './hooks/useFetch';
import { calendarDate, navigate, useLocation } from './navigation';

const SoccerPage = lazy(() => import('./pages/SoccerPage'));
const NBAPage = lazy(() => import('./pages/NBAPage'));
const NFLPage = lazy(() => import('./pages/NFLPage'));
const MatchAnalysisPage = lazy(() => import('./pages/MatchAnalysisPage'));
const InsightsPage = lazy(() => import('./pages/InsightsPage'));

export type DashPage = 'Dashboard' | 'Soccer' | 'NBA' | 'NFL' | 'Match Analysis' | 'Insights';
const paths: Record<DashPage, string> = { Dashboard: '/', Soccer: '/soccer', NBA: '/nba', NFL: '/nfl', 'Match Analysis': '/match-analysis', Insights: '/insights' };

function MatchRoute({ search }: { search: string }) {
  const params = new URLSearchParams(search);
  const id = params.get('match_id');
  const { data, loading, error, retry } = useFetch<{ decision: Decision }>(id ? `/api/matches/${encodeURIComponent(id)}?${params}` : null);
  if (id && loading) return <CardSkeleton />;
  if (error) return <RequestError message={error} onRetry={retry} />;
  const decision = data?.decision ?? null;
  return <MatchAnalysisPage decision={decision} sport={decision?.sport} teamAId={decision?.homeId} teamBId={decision?.awayId} leagueId={decision?.leagueId} />;
}

export default function App() {
  const location = useLocation();
  const [rawPath, search = ''] = location.split('?');
  const path = rawPath.length > 1 ? rawPath.replace(/\/$/, '') : rawPath;
  const page = (Object.keys(paths) as DashPage[]).find(item => paths[item] === path) ?? (path === '/prediction' ? 'Match Analysis' : null);

  function selectMatch(decision: Decision) {
    const params = new URLSearchParams({ sport: decision.sport ?? 'soccer' });
    if (decision.matchId) params.set('match_id', decision.matchId);
    if (decision.leagueId) params.set('league_id', String(decision.leagueId));
    if (decision.slateDate || decision.matchDate) params.set('date', decision.slateDate || calendarDate(decision.matchDate!));
    navigate(`/match-analysis?${params}`);
  }

  let content;
  switch (page) {
    case 'Dashboard': content = <HomePage onSelectMatch={selectMatch} />; break;
    case 'Soccer': content = <SoccerPage onSelectMatch={selectMatch} />; break;
    case 'NBA': content = <NBAPage onSelectMatch={selectMatch} />; break;
    case 'NFL': content = <NFLPage onSelectMatch={selectMatch} />; break;
    case 'Insights': content = <InsightsPage onSelectMatch={selectMatch} />; break;
    case 'Match Analysis': content = <MatchRoute key={search} search={search} />; break;
    default: content = <RequestError message="This page was not found." onRetry={() => navigate('/')} />;
  }
  return <DashboardLayout activeItem={page ?? 'Page not found'} onNavigate={item => navigate(paths[item as DashPage])}><div className="route-transition" key={path}><Suspense fallback={<CardSkeleton />}>{content}</Suspense></div></DashboardLayout>;
}
