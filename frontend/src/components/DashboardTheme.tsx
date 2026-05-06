import { useEffect, useState, type ReactNode } from 'react';
import { Activity, Home, Search, TrendingUp } from 'lucide-react';
import scorpredMark from '../assets/scorpred-player-logo.png';

interface NavItem {
  label: string;
  icon: ReactNode;
}

const NAV_ITEMS: NavItem[] = [
  { label: 'Home',           icon: <Home className="h-4 w-4" /> },
  { label: 'Soccer',         icon: <SoccerIcon /> },
  { label: 'NBA',            icon: <BasketballIcon /> },
  { label: 'Match Analysis', icon: <Search className="h-4 w-4" /> },
  { label: 'Insights',       icon: <TrendingUp className="h-4 w-4" /> },
];

function SoccerIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="m9 8 3-2 3 2 1 4-4 3-4-3 1-4Z" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function BasketballIcon() {
  return (
    <svg viewBox="0 0 24 24" className="h-4 w-4" aria-hidden="true">
      <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeWidth="1.8" />
      <path d="M3.5 12h17M12 3c2.2 2.3 3.3 5.3 3.3 9S14.2 18.7 12 21M12 3C9.8 5.3 8.7 8.3 8.7 12S9.8 18.7 12 21"
        fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function LiveClock() {
  const [time, setTime] = useState(() => new Date());
  useEffect(() => {
    const id = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(id);
  }, []);
  return (
    <span className="live-chip">
      <span className="live-dot" />
      {time.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
    </span>
  );
}

export default function DashboardLayout({
  children,
  activeItem = 'Home',
  onNavigate,
}: {
  children: ReactNode;
  activeItem?: string;
  onNavigate?: (item: string) => void;
}) {
  return (
    <div className="app-layout">
      {/* ── Desktop sidebar ──────────────────────────── */}
      <aside className="sidebar hidden md:block">
        <div className="sidebar-inner">
          {/* Brand block */}
          <div className="sidebar-brand">
            <div className="sidebar-logo">
              <img src={scorpredMark} alt="ScorPred" className="h-full w-full object-cover" />
            </div>
            <p className="sidebar-title">ScorPred</p>
            <p className="sidebar-subtitle">Decision Intelligence</p>
          </div>

          {/* Navigation */}
          <nav className="sidebar-nav">
            {NAV_ITEMS.map((item) => {
              const active = item.label === activeItem;
              return (
                <button
                  key={item.label}
                  type="button"
                  onClick={() => onNavigate?.(item.label)}
                  className={`nav-item ${active ? 'nav-item-active' : ''}`}
                >
                  <span className="nav-icon">{item.icon}</span>
                  <span>{item.label}</span>
                </button>
              );
            })}
          </nav>

          {/* Footer */}
          <div className="sidebar-footer">
            <p className="text-[11px] leading-relaxed text-slate-600">
              Clear actions, confidence, and trust signals for every slate.
            </p>
          </div>
        </div>
      </aside>

      {/* ── Content area ────────────────────────────── */}
      <div className="content-area">
        <header className="topbar">
          <div>
            <p className="page-eyebrow">{activeItem === 'Home' ? 'ScorPred' : 'ScorPred'}</p>
            <h1 className="font-oswald text-[17px] uppercase tracking-[0.07em] text-white leading-tight">
              {activeItem}
            </h1>
          </div>
          <div className="flex items-center gap-3">
            <span className="status-chip hidden sm:inline-flex">
              <Activity className="h-3.5 w-3.5 text-emerald-400" />
              Data-aware
            </span>
            <LiveClock />
          </div>
        </header>

        {/* Mobile bottom tab bar */}
        <nav className="mobile-tab-bar md:hidden">
          {NAV_ITEMS.map((item) => {
            const active = item.label === activeItem;
            return (
              <button
                key={item.label}
                type="button"
                onClick={() => onNavigate?.(item.label)}
                className={`mobile-tab ${active ? 'mobile-tab-active' : ''}`}
              >
                <span className="mobile-tab-icon">{item.icon}</span>
                <span className="mobile-tab-label">{item.label}</span>
              </button>
            );
          })}
        </nav>

        <main className="main-content">{children}</main>
      </div>
    </div>
  );
}

export function DashboardCard({
  title,
  children,
  className = '',
}: {
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <section className={`card ${className}`}>
      {title && <p className="section-label mb-3">{title}</p>}
      {children}
    </section>
  );
}
