import { Component, lazy, Suspense, useEffect, useRef, useState, useSyncExternalStore, type ReactNode } from 'react';

const ArenaScene = lazy(() => import('./ArenaScene'));
export type ArenaSport = 'nfl' | 'nba' | 'soccer';

function useMedia(query: string) {
  return useSyncExternalStore(callback => {
    const media = matchMedia(query); media.addEventListener('change', callback);
    return () => media.removeEventListener('change', callback);
  }, () => matchMedia(query).matches);
}

function FlatArena({ sport }: { sport: ArenaSport }) {
  return <div className={`arena-flat arena-flat-${sport}`} data-renderer="lite" aria-hidden="true"><div className="flat-stadium"><div className="flat-pitch">
    <svg viewBox="0 0 600 330" fill="none"><rect x="20" y="20" width="560" height="290" rx="2" />
      {sport === 'nfl' ? <>{Array.from({ length: 9 }, (_, index) => <path key={index} d={`M${76 + index * 56} 20v290`} />)}<path d="M76 135h448M76 195h448" strokeDasharray="2 12" /></>
        : <><path d="M300 20v290" /><circle cx="300" cy="165" r="44" />
          {sport === 'soccer' ? <path d="M20 80h90v170H20m560-170h-90v170h90M20 120h32v90H20m560-90h-32v90h32" />
            : <><path d="M20 100h110v130H20m560-130H470v130h110M20 50h75a155 155 0 0 1 0 230H20m560-230h-75a155 155 0 0 0 0 230h75" /><circle cx="130" cy="165" r="40" /><circle cx="470" cy="165" r="40" /></>}
        </>}
    </svg><div className={`flat-ball flat-ball-${sport}`} /></div></div></div>;
}

class ArenaBoundary extends Component<{ children: ReactNode; fallback: ReactNode; onFailure: () => void }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  componentDidCatch() { this.props.onFailure(); }
  render() { return this.state.failed ? this.props.fallback : this.props.children; }
}

export default function SportsArena({ sport, compact = false }: { sport: ArenaSport; compact?: boolean }) {
  const element = useRef<HTMLDivElement>(null);
  const reduced = useMedia('(prefers-reduced-motion: reduce)');
  const mobile = useMedia('(max-width: 600px)');
  const [visible, setVisible] = useState(false);
  const [foreground, setForeground] = useState(document.visibilityState === 'visible');
  const [ready, setReady] = useState(false);
  const [failed, setFailed] = useState(false);
  const [side, setSide] = useState<'home' | 'away'>('home');
  const [lite, setLite] = useState(() => {
    try { return localStorage.getItem('scorpred-graphics') === 'lite' || new URLSearchParams(location.search).get('graphics') === 'lite'; }
    catch { return true; }
  });
  useEffect(() => {
    const observer = new IntersectionObserver(entries => setVisible(entries[0].isIntersecting), { rootMargin: '80px' });
    if (element.current) observer.observe(element.current);
    const visibility = () => setForeground(document.visibilityState === 'visible');
    document.addEventListener('visibilitychange', visibility);
    return () => { observer.disconnect(); document.removeEventListener('visibilitychange', visibility); };
  }, []);
  useEffect(() => {
    if (!visible || lite || reduced || failed) return;
    const timer = setTimeout(() => setReady(true), 900);
    return () => clearTimeout(timer);
  }, [visible, lite, reduced, failed]);
  const render3D = ready && !lite && !reduced && !failed;
  const active = render3D && visible && foreground;
  const fallback = <FlatArena sport={sport} />;
  return <div ref={element} className={`sports-arena arena-${sport}${compact ? ' arena-compact' : ''}`} data-active={active} data-side={side} aria-label={`Interactive ${sport === 'nba' ? 'basketball court' : sport === 'nfl' ? 'football field' : 'soccer pitch'}`}>
    <div className="arena-grid" aria-hidden="true" />
    {render3D ? <ArenaBoundary onFailure={() => setFailed(true)} fallback={fallback}><Suspense fallback={fallback}>
      <ArenaScene sport={sport} active={active} side={side} onSelect={() => setSide(value => value === 'home' ? 'away' : 'home')} dpr={mobile ? 1 : 1.5} />
    </Suspense></ArenaBoundary> : fallback}
    <div className="arena-toolbar"><span className="arena-label">{sport === 'nba' ? 'COURTSIDE' : sport === 'nfl' ? 'THE GRIDIRON' : 'THE PITCH'}<span>VENUE ILLUSTRATION</span></span>
      <button className="arena-mode" disabled={reduced || failed} onClick={() => {
        setLite(value => { try { localStorage.setItem('scorpred-graphics', value ? '3d' : 'lite'); } catch { /* Preference is optional. */ } return !value; });
      }}>{reduced ? 'Reduced motion' : failed ? 'Lite view · WebGL unavailable' : lite ? 'Enable 3D' : 'Use lite view'}</button>
    </div>
    <div className="arena-bottom"><span>{render3D ? 'Move pointer to explore · select the ball' : 'Lightweight arena view'}<small>Illustration · not player tracking</small></span>
      <div className="arena-view-controls" aria-label="Arena perspective"><button aria-pressed={side === 'home'} onClick={() => setSide('home')}>Home view</button><button aria-pressed={side === 'away'} onClick={() => setSide('away')}>Away view</button></div>
    </div>
  </div>;
}
