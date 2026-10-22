import type { Decision } from './DecisionCard';
import { calendarFormat } from '../navigation';
import { useNow } from '../hooks/useNow';

/** Source observation time is never replaced by the time a page was rendered. */
export default function DataStatus({ cards, updated, loading, warnings = [] }: {
  cards: Decision[]; updated?: string | null; loading?: boolean; warnings?: string[];
}) {
  const now = useNow();
  const sources = cards.map(card => card.dataFreshness);
  const dates = sources.map(source => source?.observed_at).filter((value): value is string => Boolean(value));
  if (updated) dates.push(updated);
  const observed = dates.filter(value => Number.isFinite(Date.parse(value))).sort((a, b) => Date.parse(a) - Date.parse(b))[0];
  const delayed = sources.some(source => !source || source.state !== 'fresh'
    || !Number.isFinite(Date.parse(source.expires_at || '')) || Date.parse(source.expires_at || '') <= now);
  return <div className="data-status" aria-label="Data availability">
    <p className="quiet-label">{loading ? 'Checking available data…' : observed
      ? `Source observed ${calendarFormat(observed, { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' })} ET${delayed ? ' · Update needed; estimates may be unavailable' : ''}`
      : 'Source observation time unavailable. Check individual matchup availability.'}</p>
    {warnings.map(warning => <p key={warning} className="coverage-note">{warning}</p>)}
  </div>;
}
