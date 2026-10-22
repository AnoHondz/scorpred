import { ShieldCheck, Scale } from 'lucide-react';
import { useFetch } from '../hooks/useFetch';
import RequestError from './RequestError';
import { CardSkeleton } from './DecisionCard';

interface SportRecord {
  graded: number;
  correct: number;
  accuracy: number | null;
  accuracy_95ci: [number, number] | null;
  pending: number;
  excluded: { recorded_after_kickoff: number; no_kickoff_time: number; preseason: number };
  sample_status: 'sufficient' | 'insufficient';
}

interface MarketBenchmark {
  test_window: { start: string; end: string };
  matches: number;
  model_accuracy: number;
  market_accuracy: number;
  log_loss_gap: number;
  log_loss_gap_95ci: [number, number];
  model_pick_roi: number;
  model_pick_roi_95ci: [number, number];
  value_bet_roi: number;
  value_bet_roi_95ci: [number, number];
  value_bets: number;
}

interface TrackRecordData {
  minimum_sample: number;
  sports: Record<'soccer' | 'nba', SportRecord>;
  market_benchmark: MarketBenchmark | null;
  notes: string[];
}

const pct = (value: number, digits = 1) => `${(value * 100).toFixed(digits)}%`;
const signedPct = (value: number) => `${value > 0 ? '+' : ''}${pct(value)}`;
const range = (values: [number, number], format: (value: number) => string) => `${format(values[0])} to ${format(values[1])}`;

function SportRow({ label, record, minimum }: { label: string; record: SportRecord; minimum: number }) {
  const excluded = record.excluded.recorded_after_kickoff + record.excluded.no_kickoff_time + record.excluded.preseason;
  return <tr>
    <th scope="row">{label}</th>
    <td>{record.graded ? `${record.correct} of ${record.graded}` : 'None yet'}</td>
    <td>{record.accuracy == null ? '—' : pct(record.accuracy)}</td>
    <td>{record.accuracy_95ci ? range(record.accuracy_95ci, value => pct(value, 0)) : '—'}</td>
    <td>{record.sample_status === 'sufficient' ? 'Sufficient' : `Needs ${minimum - record.graded} more`}</td>
    <td>{record.pending}</td>
    <td>{excluded}</td>
  </tr>;
}

export default function TrackRecord() {
  const { data, loading, error, retry } = useFetch<TrackRecordData>('/api/performance/track-record');
  if (loading) return <CardSkeleton />;
  if (error || !data) return <RequestError message={error ?? 'The track record is unavailable.'} onRetry={retry} />;
  const { sports, market_benchmark: market, minimum_sample: minimum } = data;
  return <section className="section historical-performance" aria-label="Verified track record">
    <div className="section-heading-row"><div><p className="page-eyebrow"><ShieldCheck size={14} />VERIFIED TRACK RECORD</p>
      <h2 className="section-title">Picks graded against real results.</h2></div></div>
    <p className="page-description">Only picks recorded before kickoff count. Picks logged after a game started are excluded and listed below, so the record cannot be improved after the fact.</p>

    <div className="card evaluation-table-card"><div className="section-heading-row"><h3 className="panel-title">Rule-engine winner picks</h3><span className="quiet-label">{minimum} graded picks needed per sport before accuracy is meaningful</span></div>
      <div className="table-scroll"><table className="evaluation-table"><caption className="sr-only">Verified pregame rule-engine picks by sport</caption>
        <thead><tr><th scope="col">Sport</th><th scope="col">Correct</th><th scope="col">Accuracy</th><th scope="col">95% range</th><th scope="col">Sample</th><th scope="col">Pending</th><th scope="col">Excluded</th></tr></thead>
        <tbody><SportRow label="Soccer" record={sports.soccer} minimum={minimum} /><SportRow label="NBA (regular season)" record={sports.nba} minimum={minimum} /></tbody>
      </table></div>
      <p className="quiet-label">Excluded: {sports.soccer.excluded.recorded_after_kickoff + sports.nba.excluded.recorded_after_kickoff} recorded after kickoff, {sports.nba.excluded.preseason} NBA preseason. With samples this small the 95% range is wide; treat accuracy as unproven.</p>
    </div>

    {market && <div className="card evaluation-table-card"><div className="section-heading-row"><h3 className="panel-title"><Scale size={15} /> Soccer model versus bookmaker odds</h3><span className="quiet-label">{market.matches.toLocaleString()} top-five league matches · {market.test_window.start} to {market.test_window.end}</span></div>
      <div className="table-scroll"><table className="evaluation-table"><caption className="sr-only">Soccer model compared with closing market prices</caption>
        <thead><tr><th scope="col">Measure</th><th scope="col">Result</th><th scope="col">95% range</th></tr></thead>
        <tbody>
          <tr><th scope="row">Winners picked: model / bookmakers</th><td>{pct(market.model_accuracy)} / {pct(market.market_accuracy)}</td><td>—</td></tr>
          <tr><th scope="row">Probability error versus bookmakers (log loss gap)</th><td>{market.log_loss_gap.toFixed(3)} worse</td><td>{range(market.log_loss_gap_95ci, value => value.toFixed(3))}</td></tr>
          <tr><th scope="row">Return betting every model pick</th><td>{signedPct(market.model_pick_roi)}</td><td>{range(market.model_pick_roi_95ci, signedPct)}</td></tr>
          <tr><th scope="row">Return on "value" bets ({market.value_bets.toLocaleString()} bets, 5%+ edge)</th><td>{signedPct(market.value_bet_roi)}</td><td>{range(market.value_bet_roi_95ci, signedPct)}</td></tr>
        </tbody>
      </table></div>
      <p className="quiet-label">Historical test window, flat one-unit stakes at pre-weekend market-average prices. The bookmakers were more accurate, and bets where the model disagreed with the odds lost money. No betting edge is established.</p>
    </div>}
  </section>;
}
