import { test, expect, type Page } from '@playwright/test';

// Controlled UI fixtures only; production picks continue to come from the API.
const decision = { matchId: 'props-fixture', sport: 'nfl', teamA: 'Home team', teamB: 'Away team',
  matchup: 'Home team vs Away team', side: 'Home team', confidence: 60, action: 'CONSIDER',
  data: 'Limited Data', reason: 'Experimental scoring scenarios.', eventStatus: 'pre',
  matchDate: '2026-10-25T17:00:00Z', slateDate: '2026-10-25' };
const pick = { name: 'First Receiver', team: 'HOME', position: 'WR', label: 'Receptions', market: 'receptions',
  side: 'over', line: 4.5, probability: 0.7, chance: 0.652, record: 0.4,
  ladder: { start: 0, over: [.95, .9, .8, .7, .6, .4, .2] } };
const picks = [pick, { ...pick, name: 'Second Back', position: 'RB', label: 'Rushing yards', side: 'under', line: 55.5,
  chance: 0.61, record: 0.5, ladder: null }];

async function setup(page: Page, result: unknown = { picks, data_through_week: 6, notice: '' }, status = 200, sport = 'nfl') {
  await page.clock.install({ time: new Date('2026-10-24T12:00:00Z') });
  await page.route('**/api/**', route => {
    const url = new URL(route.request().url());
    if (url.pathname === '/api/session') return route.fulfill({ json: { user: null } });
    if (url.pathname === '/api/matches/props-fixture') return route.fulfill({ json: { decision: { ...decision, sport } } });
    if (url.pathname === `/api/${sport}/matches/props-fixture/props`) {
      if (sport !== 'soccer') expect(url.searchParams.get('date')).toBe('2026-10-25');
      return status === 200 ? route.fulfill({ json: { result: typeof result === 'function' ? result() : result } }) : route.fulfill({ status, json: { error: 'Player statistics are not available yet.' } });
    }
    return route.fulfill({ status: 422, json: { error: 'Unavailable for this controlled fixture.' } });
  });
}

const matchURL = '/match-analysis?sport=nfl&match_id=props-fixture&date=2026-10-25';

test('historical targets require no manual line editing and are not presented as sportsbook prices', async ({ page }) => {
  await setup(page);
  await page.goto(matchURL);
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  await expect(props.getByRole('heading', { name: 'Player props', exact: true })).toBeVisible();
  await expect(props.locator('.pick-row')).toHaveCount(2);
  const first = props.locator('.pick-row').first();
  await expect(first).toContainText('First Receiver');
  await expect(first).toContainText('Over 4.5 Receptions');
  await expect(first).toContainText('Season record at this line: 40%');
  await expect(first.locator('.pick-chance')).toHaveText('65%');
  await expect(first).toContainText('Historical target · no sportsbook quote');
  await expect(first).toContainText('Model estimate');
  await expect(props.getByRole('spinbutton')).toHaveCount(0);
});

const quote = { bookmaker: 'DraftKings', bookmaker_key: 'draftkings', side: 'over', line: 5.5,
  decimal_odds: 1.91, implied_probability: .5236, fair_probability: .5, model_chance: .424,
  updated_at: '2026-10-24T12:00:00Z', expires_at: '2026-10-24T12:05:00Z', source: 'The Odds API' };
const sportsbook = { status: 'available', reason: '1 of 1 props matched to fresh sportsbook lines.', matched_picks: 1, total_picks: 1 };

for (const sport of ['nfl', 'nba', 'soccer']) test(`${sport} automatically shows the sportsbook target and model at that target`, async ({ page }) => {
  await setup(page, { picks: [{ ...pick, sportsbook_quotes: [quote] }], sportsbook }, 200, sport);
  await page.goto(matchURL.replace('sport=nfl', `sport=${sport}`));
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  const first = props.locator('.pick-row').first();
  await expect(first.locator('.pick-call')).toHaveText('Over 5.5 Receptions');
  await expect(first.locator('.pick-chance')).toHaveText('42%');
  await expect(first).toContainText('DraftKings · 1.91 decimal odds');
  await expect(first).toContainText('Market fair 50%');
  await expect(props).toContainText('1 of 1 props matched');
  await expect(props.getByRole('spinbutton')).toHaveCount(0);
  await first.getByText('Compare sportsbooks', { exact: true }).click();
  await expect(first).toContainText('Historical reference: Over 4.5 Receptions. Model 65%; observed record 40%.');
  for (const width of [1440, 390, 320]) {
    await page.setViewportSize({ width, height: 844 });
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(width);
  }
});

test('expired sportsbook quotes disappear and trigger one automatic refresh', async ({ page }) => {
  let requests = 0;
  await setup(page, () => ++requests === 1
    ? { picks: [{ ...pick, sportsbook_quotes: [{ ...quote, expires_at: '2026-10-24T12:00:30Z' }] }], sportsbook }
    : { picks, sportsbook: { ...sportsbook, status: 'rate_limited', reason: 'Sportsbook prices are temporarily unavailable.' } });
  await page.goto(matchURL);
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  await expect(props.locator('.pick-call').first()).toHaveText('Over 5.5 Receptions');
  await page.clock.runFor(31_000);
  await expect(props.locator('.pick-call').first()).toHaveText('Over 4.5 Receptions');
  await expect(props).not.toContainText('DraftKings');
  await expect(props).toContainText('Sportsbook prices are temporarily unavailable.');
  await page.clock.runFor(10_000);
  expect(requests).toBe(2);
});

test('a sportsbook target without a supported model estimate never reuses the historical percentage', async ({ page }) => {
  await setup(page, { picks: [{ ...pick, sportsbook_quotes: [{ ...quote, line: 5, fair_probability: null, model_chance: null }] }], sportsbook });
  await page.goto(matchURL);
  const first = page.getByRole('region', { name: 'Player props', exact: true }).locator('.pick-row').first();
  await expect(first.locator('.pick-call')).toHaveText('Over 5 Receptions');
  await expect(first.locator('.pick-chance')).toHaveText('Unavailable');
  await expect(first.locator('.pick-body > p').filter({ hasText: /Market fair/ })).toHaveCount(0);
});

test('no strong picks and unavailable data are stated plainly', async ({ page }) => {
  await setup(page, { picks: [], data_through_week: 6, notice: '' });
  await page.goto(matchURL);
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  await expect(props).toContainText('No strong picks for this game.');
});

test('missing statistics explain why props are unavailable', async ({ page }) => {
  await setup(page, null, 422);
  await page.goto(matchURL);
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  await expect(props).toContainText('Player statistics are not available yet.');
});

test('a response without picks shows an error instead of an empty panel', async ({ page }) => {
  await setup(page, { teams: [] });
  await page.goto(matchURL);
  const props = page.getByRole('region', { name: 'Player props', exact: true });
  await expect(props).toContainText('Player props returned no picks');
});
