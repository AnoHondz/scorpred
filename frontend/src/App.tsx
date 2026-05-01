import { useState } from 'react';
import DarkHUD from './components/DarkHUD';
import DashboardLayout from './components/DashboardTheme';
import HomePage from './pages/HomePage';
import SoccerPage from './pages/SoccerPage';
import NBAPage from './pages/NBAPage';
import MatchAnalysisPage from './pages/MatchAnalysisPage';
import InsightsPage from './pages/InsightsPage';
import type { Decision } from './components/DecisionCard';

type View = 'landing' | 'dashboard';

export type DashPage = 'Home' | 'Soccer' | 'NBA' | 'Match Analysis' | 'Insights';

function PageContent({
  page,
  onSelectMatch,
  selectedDecision,
}: {
  page: DashPage;
  onSelectMatch: (d: Decision) => void;
  selectedDecision: Decision | null;
}) {
  switch (page) {
    case 'Home':
      return <HomePage onSelectMatch={onSelectMatch} />;
    case 'Soccer':
      return <SoccerPage onSelectMatch={onSelectMatch} />;
    case 'NBA':
      return <NBAPage onSelectMatch={onSelectMatch} />;
    case 'Match Analysis':
      return (
        <MatchAnalysisPage
          decision={selectedDecision}
          sport={selectedDecision?.sport ?? 'soccer'}
          teamAId={selectedDecision?.homeId}
          teamBId={selectedDecision?.awayId}
          leagueId={selectedDecision?.leagueId}
        />
      );
    case 'Insights':
      return <InsightsPage />;
  }
}

export default function App() {
  const [view, setView] = useState<View>('landing');
  const [page, setPage] = useState<DashPage>('Home');
  const [selectedDecision, setSelectedDecision] = useState<Decision | null>(null);

  function handleSelectMatch(d: Decision) {
    setSelectedDecision(d);
    setPage('Match Analysis');
  }

  if (view === 'landing') {
    return (
      <button
        type="button"
        onClick={() => setView('dashboard')}
        className="block w-full cursor-pointer text-left"
        aria-label="Open ScorPred app"
      >
        <DarkHUD />
      </button>
    );
  }

  return (
    <DashboardLayout activeItem={page} onNavigate={(item) => setPage(item as DashPage)}>
      <PageContent page={page} onSelectMatch={handleSelectMatch} selectedDecision={selectedDecision} />
    </DashboardLayout>
  );
}
