import { test, expect, type Page } from '@playwright/test';

const decision = { matchId: 'score-1', teamA: 'Home team', teamB: 'Away team', matchup: 'Home team vs Away team',
  side: 'Home team', confidence: 55, action: 'CONSIDER', data: 'Partial Data', reason: 'Compare scoring evidence.',
  sport: 'soccer', homeId: 1, awayId: 2, leagueId: 39, matchDate: '2027-01-01T15:00:00Z' };
const research = { available: true, model: 'test_research', projected_score: { home: 1.8, away: 1.1, total: 2.9 },
  intervals: { home: { low: 0, high: 3 }, away: { low: 0, high: 2 } }, notice: 'Retrospective evaluation only.',
  validation: { status: 'retrospective_holdout', test_games: 400, points_mae: .9, baseline_mae: 1.0, interval_coverage: { home: .81, away: .79 }, test_end: '2026-06-01' },
  references: [{ title: 'Research paper', url: 'https://doi.org/10.1111/1467-9876.00065' }] };
const primary = { line: 2.5, over_prob: 55, under_prob: 45, lean: 'OVER' };
const top = { home: 2, away: 1, score: '2-1', prob: 9.5, result: 'H' };
const soccer = { sport: 'soccer', team_a: 'Home team', team_b: 'Away team', model: 'test_research', research,
  projected_score: research.projected_score, lambda_a: 1.8, lambda_b: 1.1,
  most_likely_score: top, top_scorelines: [top], matrix_grid: [top], win_probabilities: { home: 55, draw: 25, away: 20 },
  over_under: [primary], primary_ou_line: primary, btts: { yes: 51, no: 49 } };

async function setup(page: Page, sport = 'soccer', extra: Record<string, unknown> = {}) {
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/session') return route.fulfill({ json: { user: null } });
    if (path === '/api/matches/score-1') return route.fulfill({ json: { decision: { ...decision, sport, ...extra } } });
    return route.fulfill({ status: 503, json: { error: 'Not part of this scoring check.' } });
  });
}

test('soccer separates expected goals from exact scores and shows research and uncertainty', async ({ page }) => {
  await setup(page);
  await page.route('**/api/scoreline/soccer?*', route => {
    expect(new URL(route.request().url()).searchParams.get('before')).toBe(decision.matchDate);
    return route.fulfill({ json: { status: 'ok', result: soccer } });
  });
  await page.goto('/match-analysis?sport=soccer&match_id=score-1');
  const predictor = page.getByLabel('Scoring predictor', { exact: true });
  await expect(predictor.getByLabel('Projected score')).toContainText('1.8');
  await expect(predictor).toContainText('Most likely scoreline');
  await expect(predictor.getByLabel('Score prediction ranges')).toContainText('80% target range');
  await expect(predictor).toContainText('Later-game test: 400 games');
  await expect(predictor.getByRole('link', { name: /Research paper/ })).toHaveAttribute('href', 'https://doi.org/10.1111/1467-9876.00065');
  await page.setViewportSize({ width: 320, height: 720 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(320);
  await page.reload();
  await expect(predictor.getByLabel('Projected score')).toContainText('1.8');
});

test('malformed scoring response displays an error and retry recovers without a page crash', async ({ page }) => {
  await setup(page);
  const errors: string[] = [];
  page.on('pageerror', error => errors.push(error.message));
  let recover = false;
  await page.route('**/api/scoreline/soccer?*', route => route.fulfill({ json: { status: 'ok', result: recover ? soccer : { sport: 'soccer', projected_score: {} } } }));
  await page.goto('/match-analysis?sport=soccer&match_id=score-1');
  await expect(page.getByRole('alert')).toContainText('incomplete data');
  recover = true;
  await page.getByRole('button', { name: 'Try again' }).click();
  await expect(page.getByLabel('Projected score')).toContainText('1.8');
  expect(errors).toEqual([]);
});

test('NBA labels projected margin correctly and does not advertise tied final scores', async ({ page }) => {
  await setup(page, 'nba');
  const nba = { ...soccer, sport: 'nba', proj_margin: 8, spread_favorite: 'Home team', sigma_total: 18,
    projected_score: { home: 114, away: 106, total: 220 }, most_likely_range: { ...top, home: 114, away: 106, score: '114-106', prob: .2 },
    top_scorelines: [{ ...top, home: 114, away: 106, score: '114-106', prob: .2 }], win_probabilities: { home: 65, away: 35 } };
  await page.route('**/api/scoreline/nba?*', route => route.fulfill({ json: { status: 'ok', result: nba } }));
  await page.goto('/match-analysis?sport=nba&match_id=score-1');
  const predictor = page.getByLabel('Scoring predictor', { exact: true });
  await expect(predictor).toContainText('Projected margin: 8.0 points');
  await expect(predictor.getByText('Draw', { exact: true })).toHaveCount(0);
  await expect(predictor.getByLabel('Projected score')).toContainText('114.0');
});

test('NFL shows the trained projection separately from descriptive scenario shares', async ({ page }) => {
  await setup(page, 'nfl');
  await page.route('**/api/nfl/matches/score-1/analysis?*', route => route.fulfill({ json: { result: {
    projected_score: { home: 20, away: 17 }, probabilities: { home: 60, draw: 5, away: 35 }, samples: { home: 5, away: 5 },
    data_source: 'nflverse', notice: 'Scenario shares are descriptive.',
    research: { ...research, projected_score: { home: 24.5, away: 20.1, total: 44.6 } },
  } } }));
  await page.goto('/match-analysis?sport=nfl&match_id=score-1');
  await expect(page.getByLabel('Experimental NFL scoring research')).toContainText('24.5');
  await expect(page.getByText('Projected points:', { exact: false })).toContainText('20.0');
  await expect(page.getByLabel('Score prediction ranges')).toBeVisible();
  await expect(page.getByRole('heading', { name: 'Recent scoring scenarios', exact: true })).toBeVisible();
});
