import http from 'k6/http';
import { check, sleep } from 'k6';
import { Counter } from 'k6/metrics';
import { BASE, SEARCH_WORDS, ensureBooks, pick } from './lib/data.js';
import { META, buildOptions } from './lib/stages.js';
import { makeSummary } from './lib/summary.js';

const cacheResult = new Counter('cache_result');
const THINK = Number(__ENV.THINK || 0);

export const options = buildOptions({
  'cache_result{x_cache:HIT}': ['count>=0'],
  'cache_result{x_cache:MISS}': ['count>=0'],
  'cache_result{x_cache:BYPASS}': ['count>=0'],
  'cache_result{x_cache:DISABLED}': ['count>=0'],
});

export function setup() {
  const books = ensureBooks();
  const all = http.get(`${BASE}/api/v1/books?limit=100`).json('items').map((b) => b.id);
  return { ids: books.concat(all) };
}

function track(res) {
  check(res, { 'status 200': (r) => r.status === 200 });
  const xc = res.headers['X-Cache'];
  if (xc) cacheResult.add(1, { x_cache: xc });
}

export default function (data) {
  const roll = Math.random();
  if (roll < 0.5) {
    track(http.get(`${BASE}/api/v1/books/${pick(data.ids)}`, { tags: { name: 'GET /books/{id}' } }));
  } else if (roll < 0.85) {
    const q = pick(SEARCH_WORDS);
    const offset = 20 * Math.floor(Math.random() * 3);
    track(http.get(`${BASE}/api/v1/books?q=${q}&limit=20&offset=${offset}`,
      { tags: { name: 'GET /books?q=' } }));
  } else {
    const days = pick([7, 30, 90]);
    track(http.get(`${BASE}/api/v1/reports/popular-books?days=${days}&limit=10`,
      { tags: { name: 'GET /reports/popular-books' } }));
  }
  if (THINK) sleep(THINK);
}

export const handleSummary = makeSummary(`Scenario A - read-intensive (${__ENV.LABEL || ''})`,
  { ...META, scenario: 'A' });
