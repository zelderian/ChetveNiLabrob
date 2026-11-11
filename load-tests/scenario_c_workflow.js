import http from 'k6/http';
import { check, group, sleep } from 'k6';
import { Trend } from 'k6/metrics';
import { BASE, JSON_HEADERS, SEARCH_WORDS, cleanupActiveLoans, ensureBooks, ensureMembers, login,
  loginAll, pick, uuid } from './lib/data.js';
import { LEVELS, META, buildOptions } from './lib/stages.js';
import { makeSummary } from './lib/summary.js';

const journey = new Trend('journey_duration', true);
const THINK = Number(__ENV.THINK || 0);
const MAX_VUS = Math.max(...LEVELS, 5);

export const options = buildOptions();
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 409));

export function setup() {
  const books = ensureBooks();
  ensureMembers(MAX_VUS);
  cleanupActiveLoans(loginAll(MAX_VUS));
  return { books };
}

export default function (data) {
  const started = Date.now();
  const token = login(__VU, { tags: { name: 'POST /auth/login' } });
  if (!check(token, { 'logged in': (t) => !!t })) return;
  const auth = { Authorization: `Bearer ${token}`, ...JSON_HEADERS };

  group('browse', () => {
    http.get(`${BASE}/api/v1/books?q=${pick(SEARCH_WORDS)}&limit=20`, { tags: { name: 'GET /books?q=' } });
  });
  const bookId = pick(data.books);
  http.get(`${BASE}/api/v1/books/${bookId}`, { tags: { name: 'GET /books/{id}' } });

  const loan = http.post(`${BASE}/api/v1/loans`, JSON.stringify({ book_id: bookId, days: 7 }),
    { headers: { ...auth, 'Idempotency-Key': uuid() }, tags: { name: 'POST /loans' } });
  http.get(`${BASE}/api/v1/me/loans?active=true`, { headers: auth, tags: { name: 'GET /me/loans' } });
  if (loan.status === 201) {
    const ret = http.post(`${BASE}/api/v1/loans/${loan.json('id')}/return`, null,
      { headers: auth, tags: { name: 'POST /loans/{id}/return' } });
    check(ret, { 'returned 200': (r) => r.status === 200 });
  }
  http.post(`${BASE}/api/v1/auth/logout`, null, { headers: auth, tags: { name: 'POST /auth/logout' } });
  journey.add(Date.now() - started);
  if (THINK) sleep(THINK);
}

export const handleSummary = makeSummary(`Scenario C - complex workflow (${__ENV.LABEL || ''})`,
  { ...META, scenario: 'C' });
