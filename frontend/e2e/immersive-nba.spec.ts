import { test, expect, type Page } from '@playwright/test';

const decision = { sport: 'nba', matchId: 'context-test', teamA: 'Home test team', teamB: 'Away test team',
  homeId: 20, awayId: 5, matchup: 'Home test team vs Away test team', side: 'Unavailable', action: 'SKIP', confidence: 0,
  reason: 'Insufficient current-season samples.', data: 'Limited Data', matchDate: '2026-10-23T23:00:00Z', eventStatus: 'pre' };
const summary = { games: 2, wins: 1, losses: 1, points_for: 102.5, points_against: 100.5, scope: 'Observed archive sample', recent_results: [] };
const team = { team: { id: '20', name: 'Home test team' }, previous: summary,
  current: { ...summary, games: 0, wins: 0, losses: 0, points_for: null, points_against: null },
  current_season: 2027, previous_season: 2026, current_status: 'unavailable', current_source: {},
  historical_source: { files: ['local-test.json'], historical_pregame_availability: 'unverified' } };

async function setup(page: Page) {
  await page.clock.install({ time: new Date('2026-10-22T12:00:00Z') });
  await page.route('**/api/**', route => {
    const path = new URL(route.request().url()).pathname;
    if (path === '/api/session') return route.fulfill({ json: { user: null } });
    if (path === '/api/matches/context-test') return route.fulfill({ json: { decision } });
    if (path === '/api/dashboard/nba') return route.fulfill({ json: { slate: [decision], topOpportunities: [], selectedDate: '2026-10-23', availableDates: ['2026-10-23'] } });
    if (path.includes('/context')) return route.fulfill({ json: { result: { version: 'nba-descriptive-context-v1', role: 'descriptive_only',
      teams: { home: team, away: { ...team, team: { id: '5', name: 'Away test team' } } }, game: {},
      statistics_cutoff: '2026-10-21T12:00:00Z', notice: 'Historical observations only; no prediction fallback.', refresh_pending: false } } });
    if (path === '/api/nba/games') return route.fulfill({ json: { slate: [decision], topOpportunities: [], selectedDate: '2026-10-23', availableDates: ['2026-10-23'] } });
    return route.fulfill({ status: 422, json: { message: 'Scoring unavailable for this controlled sample.' } });
  });
}

test('historical comparison is useful without inventing a current record or probability', async ({ page }) => {
  await setup(page);
  await page.goto('/match-analysis?sport=nba&match_id=context-test');
  const comparison = page.getByLabel('NBA team comparisons');
  await expect(comparison).toContainText('102.5');
  await expect(comparison).toContainText('Descriptive');
  expect(await comparison.evaluate(element => Boolean(element.compareDocumentPosition(document.querySelector('.analysis-layout')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await page.getByRole('button', { name: 'Current season', exact: true }).click();
  await expect(comparison).toContainText('do not establish a 0–0 season record');
  await expect(comparison).toContainText('Unavailable');
  await expect(page.getByRole('heading', { name: 'Game outlook', exact: true })).toBeVisible();
});

test('NBA overview exposes real comparisons before unavailable prediction panels', async ({ page }) => {
  await setup(page);
  await page.goto('/nba');
  const comparison = page.getByLabel('NBA team comparisons');
  await expect(comparison).toContainText('102.5');
  await expect(comparison).toContainText('Observed record');
  await expect(comparison).toContainText('missing prediction does not mean team history is missing');
  expect(await comparison.evaluate(element => Boolean(element.compareDocumentPosition(document.querySelector('.matchup-stage')!) & Node.DOCUMENT_POSITION_FOLLOWING))).toBe(true);
  await page.getByRole('button', { name: 'Open full comparison:', exact: false }).click();
  await expect(page).toHaveURL(/match_id=context-test/);
  await expect(page.getByLabel('NBA team comparisons')).toContainText('102.5');
});

test('early-season evaluation is labeled research and never requests a disabled preview', async ({ page }) => {
  await setup(page);
  const previews: string[] = [];
  page.on('request', request => { if (request.url().includes('/research/early-season/matches/')) previews.push(request.url()); });
  await page.route('**/api/nba/research/early-season', route => route.fulfill({ json: { available: true, research_enabled: false,
    report: { version: 'controlled-study', evaluated_games: 10, conclusion: 'Prospective validation is required.',
      coverage: { '2024': { early_games: 10, winner_rule_gate: 6, research_available: 10 } },
      metrics: { blend: { games: 10, log_loss: .65, brier: .23, accuracy: .6 } } } } }));
  await page.goto('/nba');
  const study = page.getByLabel('NBA early-season research study');
  await study.locator('summary').click();
  await expect(study).toContainText('10 games tested');
  await expect(study).toContainText('production predictions unchanged');
  await expect(study).toContainText('Experimental previews are disabled');
  await expect(study.getByRole('button')).toHaveCount(0);
  expect(previews).toHaveLength(0);
  await expect(page.locator('.matchup-stage')).toContainText('Unavailable');
});

test('archived NBA selection opens the existing analysis route', async ({ page }) => {
  await setup(page);
  await page.goto('/nba?view=archive');
  await page.getByRole('button', { name: /Analyze Matchup/ }).click();
  await expect(page).toHaveURL(/match_id=context-test/);
  await expect(page.getByLabel('NBA team comparisons')).toContainText('102.5');
});

test('lite scene remains interactive without loading a WebGL renderer', async ({ page }) => {
  await setup(page);
  await page.goto('/match-analysis?sport=nba&match_id=context-test');
  await expect(page.locator('.arena-flat')).toBeVisible();
  await page.getByRole('button', { name: 'Away view', exact: true }).click();
  await expect(page.locator('.sports-arena')).toHaveAttribute('data-side', 'away');
  await expect(page.locator('canvas')).toHaveCount(0);
  const resources = await page.evaluate(() => performance.getEntriesByType('resource').map(resource => resource.name));
  expect(resources.some(name => name.includes('ArenaScene'))).toBe(false);
});

test('reduced motion keeps a static lightweight venue and all data controls', async ({ page }) => {
  await page.emulateMedia({ reducedMotion: 'reduce' });
  await setup(page);
  await page.goto('/match-analysis?sport=nba&match_id=context-test');
  await expect(page.getByRole('button', { name: 'Reduced motion', exact: true })).toBeDisabled();
  await expect(page.locator('canvas')).toHaveCount(0);
  await expect(page.getByLabel('NBA team comparisons')).toContainText('102.5');
  await expect(page.getByLabel('Main navigation')).toBeVisible();
});
