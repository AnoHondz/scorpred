/**
 * ScorelinePredictor – full scoreline probability distribution widget.
 *
 * Soccer: Dixon-Coles corrected Poisson  → 7×7 heat-map + O/U table + BTTS
 * NBA:    Normal distribution blend       → projected score + O/U table + spread
 *
 * Usage:
 *   <ScorelinePredictor
 *     sport="soccer"
 *     teamAName="Barcelona"  teamBName="Real Madrid"
 *     teamAId={529}          teamBId={541}
 *     leagueId={140}
 *   />
 */

import { useEffect, useRef, useState } from 'react';

// ── Types ─────────────────────────────────────────────────────────────────────

interface OULine {
  line: number;
  over_prob: number;
  under_prob: number;
  push_prob?: number;
  lean: string;
}

interface TopScore {
  home: number;
  away: number;
  score?: string;
  prob: number;
  result?: string;
}

interface GridCell {
  home: number;
  away: number;
  score: string;
  prob: number; // percentage (0–100)
}

interface ProjectedScore {
  home: number;
  away: number;
  total: number;
}

interface WinProbSoccer {
  home: number;
  draw: number;
  away: number;
}

interface WinProbNBA {
  home: number;
  away: number;
}

interface DataCompleteness {
  score: number;
  tier: 'high' | 'medium' | 'low';
  factors: Record<string, boolean>;
}

interface MarketComparison {
  model_prob: number;
  market_prob: number;
  edge: number;
  signal: 'value' | 'caution' | 'fair';
}

interface SoccerResult {
  sport: 'soccer';
  team_a: string;
  team_b: string;
  lambda_a: number;
  lambda_b: number;
  projected_score: ProjectedScore;
  most_likely_score: TopScore;
  top_scorelines: TopScore[];
  matrix_grid: GridCell[];
  win_probabilities: WinProbSoccer;
  over_under: OULine[];
  btts: { yes: number; no: number };
  primary_ou_line: OULine;
  score_ranges: { low_0_1_goals: number; medium_2_3_goals: number; high_4_plus_goals: number };
  model: string;
  data_completeness?: DataCompleteness;
  market_comparison?: MarketComparison | null;
}

interface NBAResult {
  sport: 'nba';
  team_a: string;
  team_b: string;
  projected_score: ProjectedScore;
  proj_margin: number;
  spread_favorite: string;
  most_likely_range: TopScore | Record<string, unknown>;
  top_scorelines: TopScore[];
  win_probabilities: WinProbNBA;
  over_under: OULine[];
  primary_ou_line: OULine;
  sigma_total: number;
  model: string;
  data_completeness?: DataCompleteness;
}

type ScorelineResult = SoccerResult | NBAResult;

interface Props {
  sport: 'soccer' | 'nba';
  teamAName?: string;
  teamBName?: string;
  teamAId?: number | string;
  teamBId?: number | string;
  leagueId?: number | string;
  oddsTotal?: number;
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function leanColor(lean: string): string {
  if (lean === 'OVER') return 'text-emerald-400';
  if (lean === 'UNDER') return 'text-rose-400';
  return 'text-slate-400';
}

function leanBg(lean: string): string {
  if (lean === 'OVER') return 'bg-emerald-400/10 border-emerald-400/30';
  if (lean === 'UNDER') return 'bg-rose-400/10 border-rose-400/30';
  return 'bg-slate-500/10 border-slate-500/20';
}

function heatColor(prob: number, maxProb: number): string {
  const ratio = maxProb > 0 ? Math.min(prob / maxProb, 1) : 0;
  if (ratio > 0.7) return 'bg-emerald-400 text-slate-900';
  if (ratio > 0.45) return 'bg-emerald-500/60 text-emerald-100';
  if (ratio > 0.25) return 'bg-emerald-600/35 text-emerald-200';
  if (ratio > 0.10) return 'bg-slate-600/60 text-slate-300';
  return 'bg-slate-800/60 text-slate-500';
}

function resultLabel(result: string | undefined): string {
  if (result === 'H') return 'Home';
  if (result === 'A') return 'Away';
  if (result === 'D') return 'Draw';
  return result ?? '';
}

function resultColor(result: string | undefined): string {
  if (result === 'H') return 'text-emerald-300';
  if (result === 'A') return 'text-rose-300';
  return 'text-amber-300';
}

// ── Sub-components ────────────────────────────────────────────────────────────

function SectionHeader({ title }: { title: string }) {
  return (
    <div className="flex items-center gap-3 mb-3">
      <span className="text-[10px] font-bold tracking-widest uppercase text-slate-400">{title}</span>
      <span className="flex-1 h-px bg-white/5" />
    </div>
  );
}

function WinBar({ label, pct, color }: { label: string; pct: number; color: string }) {
  return (
    <div className="flex items-center gap-2 text-[12px]">
      <span className="w-20 shrink-0 text-slate-400 text-right truncate">{label}</span>
      <div className="flex-1 h-2 rounded-full bg-slate-700 overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${Math.min(pct, 100)}%` }} />
      </div>
      <span className="w-10 text-slate-200 font-semibold tabular-nums">{pct.toFixed(1)}%</span>
    </div>
  );
}

function OUTable({ lines, primary }: { lines: OULine[]; primary: OULine }) {
  return (
    <table className="w-full text-[11px] border-collapse">
      <thead>
        <tr className="text-slate-500 border-b border-white/5">
          <th className="text-left py-1.5 pr-2 font-medium">Line</th>
          <th className="text-right py-1.5 px-2 font-medium">Over %</th>
          <th className="text-right py-1.5 px-2 font-medium">Under %</th>
          <th className="text-right py-1.5 pl-2 font-medium">Lean</th>
        </tr>
      </thead>
      <tbody>
        {lines.map((row) => {
          const isPrimary = row.line === primary.line;
          return (
            <tr
              key={row.line}
              className={`border-b border-white/5 transition-colors ${isPrimary ? 'bg-white/[0.04]' : 'hover:bg-white/[0.02]'}`}
            >
              <td className={`py-1.5 pr-2 font-semibold tabular-nums ${isPrimary ? 'text-amber-300' : 'text-slate-300'}`}>
                {row.line.toFixed(1)}
                {isPrimary && <span className="ml-1 text-[9px] text-amber-500 uppercase tracking-wide">primary</span>}
              </td>
              <td className="py-1.5 px-2 text-right text-emerald-300 tabular-nums font-medium">{row.over_prob.toFixed(1)}%</td>
              <td className="py-1.5 px-2 text-right text-rose-300 tabular-nums font-medium">{row.under_prob.toFixed(1)}%</td>
              <td className={`py-1.5 pl-2 text-right font-bold tabular-nums ${leanColor(row.lean)}`}>{row.lean}</td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function ScoreHeatmap({
  grid,
  teamA,
  teamB,
  mostLikely,
}: {
  grid: GridCell[];
  teamA: string;
  teamB: string;
  mostLikely: { home: number; away: number };
}) {
  // Build lookup map: "home,away" → prob%
  const probMap = new Map<string, number>();
  let maxProb = 0;
  for (const cell of grid) {
    probMap.set(`${cell.home},${cell.away}`, cell.prob);
    if (cell.prob > maxProb) maxProb = cell.prob;
  }
  const SIZE = 7;

  return (
    <div>
      <div className="text-center text-[10px] text-slate-500 uppercase tracking-widest mb-1">
        ← {teamB} goals →
      </div>
      <div className="flex gap-1 items-start">
        <div
          className="text-[10px] text-slate-500 uppercase tracking-widest"
          style={{ writingMode: 'vertical-rl', transform: 'rotate(180deg)', minHeight: 80, alignSelf: 'center' }}
        >
          ← {teamA} goals →
        </div>
        <div>
          {/* Column headers (away goals) */}
          <div className="flex gap-0.5 mb-0.5 ml-5">
            {Array.from({ length: SIZE }, (_, j) => (
              <div key={j} className="w-8 text-center text-[10px] text-slate-500">{j}</div>
            ))}
          </div>
          {/* Rows (home goals) */}
          {Array.from({ length: SIZE }, (_, i) => (
            <div key={i} className="flex gap-0.5 mb-0.5 items-center">
              <div className="w-4 text-center text-[10px] text-slate-500">{i}</div>
              {Array.from({ length: SIZE }, (_, j) => {
                const prob = probMap.get(`${i},${j}`) ?? 0;
                const isBest = i === mostLikely.home && j === mostLikely.away;
                return (
                  <div
                    key={j}
                    title={`${teamA} ${i} – ${j} ${teamB}: ${prob.toFixed(2)}%`}
                    className={`w-8 h-8 rounded-[3px] flex items-center justify-center text-[9px] font-bold tabular-nums cursor-default
                      ${heatColor(prob, maxProb)}
                      ${isBest ? 'ring-1 ring-amber-400/80 ring-offset-1 ring-offset-slate-900' : ''}
                    `}
                  >
                    {prob >= 1 ? prob.toFixed(1) : ''}
                  </div>
                );
              })}
            </div>
          ))}
        </div>
      </div>
      <p className="mt-2 text-[10px] text-slate-600 text-center">
        Values show % probability per scoreline. Gold ring = most likely.
      </p>
    </div>
  );
}

function TopScorelines({ scores, teamA, teamB }: { scores: TopScore[]; teamA: string; teamB: string }) {
  return (
    <div className="space-y-1">
      {scores.slice(0, 8).map((s, idx) => (
        <div
          key={idx}
          className={`flex items-center gap-2 rounded-lg px-3 py-2 text-[12px] border
            ${idx === 0 ? 'bg-amber-400/8 border-amber-400/25' : 'bg-white/[0.03] border-white/[0.06]'}
          `}
        >
          <span className="w-5 text-slate-500 tabular-nums">{idx + 1}.</span>
          <span className={`font-bold tabular-nums ${idx === 0 ? 'text-amber-300' : 'text-slate-200'}`}>
            {s.score ?? `${s.home}–${s.away}`}
          </span>
          <span className={`text-[10px] ml-1 ${resultColor(s.result)}`}>
            {resultLabel(s.result)}
          </span>
          <div className="ml-auto flex items-center gap-1">
            <div
              className="h-1.5 rounded-full bg-amber-400/50"
              style={{ width: Math.max(4, (s.prob / (scores[0]?.prob || 1)) * 48) }}
            />
            <span className="text-slate-400 tabular-nums">{s.prob.toFixed(1)}%</span>
          </div>
        </div>
      ))}
      {/* Legend */}
      <div className="flex gap-4 pt-1 pl-1 text-[10px] text-slate-600">
        <span><span className="text-emerald-300">Home</span> win</span>
        <span><span className="text-amber-300">Draw</span></span>
        <span><span className="text-rose-300">Away</span> win</span>
      </div>
    </div>
  );
}

// ── Soccer view ───────────────────────────────────────────────────────────────

function SoccerView({ data }: { data: SoccerResult }) {
  const { win_probabilities: wp, btts, projected_score: ps } = data;

  return (
    <div className="space-y-5">
      {/* Projected score chips */}
      <div className="flex flex-wrap gap-3 justify-center">
        <div className="rounded-xl border border-white/8 bg-white/[0.04] px-6 py-4 text-center min-w-[160px]">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Projected Score</p>
          <p className="text-3xl font-bold text-white font-[Oswald,sans-serif] tracking-wider">
            {ps.home.toFixed(1)} – {ps.away.toFixed(1)}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">
            Total {ps.total.toFixed(1)} &nbsp;·&nbsp; λ {data.lambda_a.toFixed(2)} / {data.lambda_b.toFixed(2)}
          </p>
        </div>

        {/* Primary O/U */}
        <div className={`rounded-xl border px-6 py-4 text-center min-w-[140px] ${leanBg(data.primary_ou_line.lean)}`}>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">O/U 2.5</p>
          <p className={`text-2xl font-bold ${leanColor(data.primary_ou_line.lean)}`}>{data.primary_ou_line.lean}</p>
          <p className="text-[11px] text-slate-400 mt-1">{data.primary_ou_line.line.toFixed(1)} goals</p>
          <p className="text-[10px] text-slate-500">
            O: {data.primary_ou_line.over_prob.toFixed(1)}% / U: {data.primary_ou_line.under_prob.toFixed(1)}%
          </p>
        </div>

        {/* BTTS */}
        <div className="rounded-xl border border-white/8 bg-white/[0.04] px-6 py-4 text-center min-w-[120px]">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-2">BTTS</p>
          <p className={`text-xl font-bold ${btts.yes >= 50 ? 'text-emerald-400' : 'text-rose-400'}`}>
            {btts.yes >= 50 ? 'YES' : 'NO'}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Yes {btts.yes.toFixed(1)}% / No {btts.no.toFixed(1)}%</p>
        </div>
      </div>

      {/* Win probabilities */}
      <div>
        <SectionHeader title="Win Probabilities" />
        <div className="space-y-2">
          <WinBar label={data.team_a} pct={wp.home} color="bg-emerald-500" />
          <WinBar label="Draw" pct={wp.draw} color="bg-amber-500" />
          <WinBar label={data.team_b} pct={wp.away} color="bg-rose-500" />
        </div>
      </div>

      {/* Most likely scorelines */}
      <div>
        <SectionHeader title="Most Likely Scorelines" />
        <TopScorelines scores={data.top_scorelines} teamA={data.team_a} teamB={data.team_b} />
      </div>

      {/* Heat-map */}
      <div>
        <SectionHeader title="Scoreline Heat-Map" />
        <div className="overflow-x-auto">
          <ScoreHeatmap
            grid={data.matrix_grid}
            teamA={data.team_a}
            teamB={data.team_b}
            mostLikely={data.most_likely_score}
          />
        </div>
      </div>

      {/* O/U table */}
      <div>
        <SectionHeader title="Over / Under Lines" />
        <div className="overflow-x-auto">
          <OUTable lines={data.over_under} primary={data.primary_ou_line} />
        </div>
      </div>

      {/* Market comparison */}
      {data.market_comparison && (
        <div className="rounded-lg border-l-2 border-teal-500/30 bg-teal-500/[0.03] p-4">
          <h3 className="text-[11px] uppercase tracking-wider text-slate-500 mb-3 font-semibold">
            Market Edge Analysis
          </h3>
          <div className="flex items-center justify-between gap-4">
            <div className="space-y-1">
              <p className="text-[12px] text-slate-400">
                Model: <strong className="text-slate-200">{data.market_comparison.model_prob}%</strong>
              </p>
              <p className="text-[12px] text-slate-400">
                Market: <strong className="text-slate-200">{data.market_comparison.market_prob}%</strong>
              </p>
            </div>
            <div className={`text-right ${
              data.market_comparison.edge > 0 ? 'text-emerald-400' : 'text-rose-400'
            }`}>
              <p className="text-2xl font-bold tabular-nums">
                {data.market_comparison.edge > 0 ? '+' : ''}{data.market_comparison.edge}%
              </p>
              <p className="text-[10px] uppercase tracking-wider font-semibold mt-0.5">
                {data.market_comparison.signal}
              </p>
            </div>
          </div>
        </div>
      )}

      <p className="text-[10px] text-slate-600 text-right">Model: {data.model}</p>
    </div>
  );
}

// ── NBA view ──────────────────────────────────────────────────────────────────

function NBAView({ data }: { data: NBAResult }) {
  const { win_probabilities: wp } = data;
  const proj = data.projected_score;
  const likelyRange = data.most_likely_range as TopScore | undefined;

  return (
    <div className="space-y-5">
      {/* Projected score */}
      <div className="flex flex-wrap gap-3 justify-center">
        <div className="rounded-xl border border-white/8 bg-white/[0.04] px-6 py-4 text-center min-w-[220px]">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Projected Score</p>
          <p className="text-3xl font-bold text-white font-[Oswald,sans-serif] tracking-wider">
            {proj.home.toFixed(0)} – {proj.away.toFixed(0)}
          </p>
          <p className="text-[10px] text-slate-500 mt-1">Total: {proj.total.toFixed(1)} pts</p>
        </div>

        {/* Spread */}
        <div className="rounded-xl border border-white/8 bg-white/[0.04] px-6 py-4 text-center min-w-[140px]">
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Spread Favorite</p>
          <p className="text-xl font-bold text-amber-300">{data.spread_favorite}</p>
          <p className="text-[10px] text-slate-500 mt-1">Margin ±{data.sigma_total.toFixed(1)} pts σ</p>
        </div>

        {/* Primary O/U */}
        <div className={`rounded-xl border px-6 py-4 text-center min-w-[140px] ${leanBg(data.primary_ou_line.lean)}`}>
          <p className="text-[10px] text-slate-500 uppercase tracking-widest mb-1">Primary O/U</p>
          <p className={`text-2xl font-bold ${leanColor(data.primary_ou_line.lean)}`}>{data.primary_ou_line.lean}</p>
          <p className="text-[11px] text-slate-400 mt-1">{data.primary_ou_line.line.toFixed(1)} pts</p>
          <p className="text-[10px] text-slate-500">
            O: {data.primary_ou_line.over_prob.toFixed(1)}% / U: {data.primary_ou_line.under_prob.toFixed(1)}%
          </p>
        </div>
      </div>

      {/* Most likely total range */}
      {likelyRange && 'home' in likelyRange && (
        <div className="text-center">
          <span className="inline-block text-[11px] text-slate-400 border border-white/10 rounded-full px-4 py-1">
            Most likely score: <strong className="text-slate-200">{likelyRange.score ?? `${likelyRange.home}–${likelyRange.away}`}</strong>
            <span className="ml-2 text-slate-500">({likelyRange.prob.toFixed(1)}%)</span>
          </span>
        </div>
      )}

      {/* Win probabilities */}
      <div>
        <SectionHeader title="Win Probabilities" />
        <div className="space-y-2">
          <WinBar label={data.team_a} pct={wp.home} color="bg-emerald-500" />
          <WinBar label={data.team_b} pct={wp.away} color="bg-rose-500" />
        </div>
      </div>

      {/* Top score pairs */}
      <div>
        <SectionHeader title="Most Likely Score Combinations" />
        <TopScorelines scores={data.top_scorelines} teamA={data.team_a} teamB={data.team_b} />
      </div>

      {/* O/U table */}
      <div>
        <SectionHeader title="Over / Under Lines" />
        <div className="overflow-x-auto">
          <OUTable lines={data.over_under} primary={data.primary_ou_line} />
        </div>
      </div>

      <p className="text-[10px] text-slate-600 text-right">Model: {data.model}</p>
    </div>
  );
}

// ── Main component ────────────────────────────────────────────────────────────

export default function ScorelinePredictor({
  sport,
  teamAName = 'Home',
  teamBName = 'Away',
  teamAId,
  teamBId,
  leagueId,
  oddsTotal,
}: Props) {
  const [data, setData] = useState<ScorelineResult | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;

    setLoading(true);
    setError(null);
    setData(null);

    const endpoint = sport === 'nba' ? '/api/scoreline/nba' : '/api/scoreline/soccer';
    const body: Record<string, unknown> = { team_a_name: teamAName, team_b_name: teamBName };
    if (teamAId) body.team_a_id = teamAId;
    if (teamBId) body.team_b_id = teamBId;
    if (leagueId) body.league_id = leagueId;
    if (oddsTotal) body.odds_total = oddsTotal;

    fetch(endpoint, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
      signal: ctrl.signal,
    })
      .then((r) => r.json())
      .then((json) => {
        if (json.status === 'ok' && json.result) {
          setData(json.result as ScorelineResult);
        } else {
          setError(json.message || 'Failed to load scoreline data.');
        }
        setLoading(false);
      })
      .catch((err) => {
        if (err.name !== 'AbortError') {
          setError('Network error. Could not reach the scoreline service.');
          setLoading(false);
        }
      });

    return () => ctrl.abort();
  }, [sport, teamAName, teamBName, teamAId, teamBId, leagueId, oddsTotal]);

  return (
    <div className="card">
      <div className="section-header mb-4">
        <div className="flex items-center gap-2">
          <p className="section-label">
            Scoreline Predictor
            <span className="ml-2 text-[9px] text-slate-600 uppercase tracking-widest font-normal">
              {sport === 'nba' ? 'Normal dist.' : 'Poisson + ML blend'}
            </span>
          </p>
          {data?.data_completeness && (
            <span className={`px-2 py-0.5 text-[10px] font-semibold rounded-full border whitespace-nowrap ${
              data.data_completeness.tier === 'high'
                ? 'text-emerald-300 border-emerald-400/30 bg-emerald-400/10'
                : data.data_completeness.tier === 'medium'
                ? 'text-amber-300 border-amber-400/30 bg-amber-400/10'
                : 'text-rose-300 border-rose-400/30 bg-rose-400/10'
            }`}>
              {data.data_completeness.tier.toUpperCase()} CONFIDENCE
            </span>
          )}
        </div>
        <div className="section-divider" />
      </div>

      {loading && (
        <div className="py-10 flex flex-col items-center gap-3">
          <div className="w-8 h-8 rounded-full border-2 border-emerald-400/30 border-t-emerald-400 animate-spin" />
          <p className="text-[12px] text-slate-500">Computing scoreline distribution…</p>
        </div>
      )}

      {error && !loading && (
        <div className="rounded-lg border border-rose-400/20 bg-rose-400/5 px-4 py-3">
          <p className="text-[12px] text-rose-300">{error}</p>
        </div>
      )}

      {data && !loading && (
        data.sport === 'soccer'
          ? <SoccerView data={data as SoccerResult} />
          : <NBAView data={data as NBAResult} />
      )}
    </div>
  );
}
