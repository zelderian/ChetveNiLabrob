// Lab 5 - Scenario B: WRITE-INTENSIVE.
// Resource profile: DB transactions, row locks (SELECT ... FOR UPDATE),
// WAL / fsync I/O, cache invalidations. Every VU is its own authenticated member.
// Per iteration:
//   75 %  borrow a random book (POST /loans + Idempotency-Key) and return it
//         (POST /loans/{id}/return)  -> 2 transactional writes, 2 row locks each
//   25 %  create a new book (POST /books)  -> plain INSERT
// 409 is a legitimate business answer (e.g. limit reached) and is not an error.
//
//   k6 run load-tests/scenario_b_write.js
import http from 'k6/http';
import { check, sleep } from 'k6';
import { Rate } from 'k6/metrics';
import { BASE, JSON_HEADERS, cleanupActiveLoans, ensureBooks, ensureMembers, loginAll, pick, uuid }
  from './lib/data.js';
import { LEVELS, META, buildOptions } from './lib/stages.js';
import { makeSummary } from './lib/summary.js';

const businessConflict = new Rate('business_conflict');
const THINK = Number(__ENV.THINK || 0);
const MAX_VUS = Math.max(...LEVELS, 5);

export const options = buildOptions({ business_conflict: ['rate>=0'] });
http.setResponseCallback(http.expectedStatuses({ min: 200, max: 299 }, 409));

export function setup() {
  const books = ensureBooks();
  ensureMembers(MAX_VUS);
  const tokens = loginAll(MAX_VUS);
  cleanupActiveLoans(tokens);
  return { books, tokens, run: Math.floor(Math.random() * 9000) + 1000 };
}

export default function (data) {
  const auth = { Authorization: `Bearer ${data.tokens[(__VU - 1) % data.tokens.length]}`, ...JSON_HEADERS };

  if (Math.random() < 0.75) {
    const r = http.post(`${BASE}/api/v1/loans`, JSON.stringify({ book_id: pick(data.books), days: 14 }),
      { headers: { ...auth, 'Idempotency-Key': uuid() }, tags: { name: 'POST /loans' } });
    businessConflict.add(r.status === 409);
    if (check(r, { 'borrowed 201': (x) => x.status === 201 })) {
      const ret = http.post(`${BASE}/api/v1/loans/${r.json('id')}/return`, null,
        { headers: auth, tags: { name: 'POST /loans/{id}/return' } });
      check(ret, { 'returned 200': (x) => x.status === 200 });
    }
  } else {
    // 13-digit ISBN unique per run/VU/iteration: 9 + run(4) + vu(3) + iter(5)
    const isbn = `9${data.run}${String(__VU).padStart(3, '0')}${String(__ITER % 100000).padStart(5, '0')}`;
    const r = http.post(`${BASE}/api/v1/books`, JSON.stringify({
      isbn, title: `Write Test ${isbn}`, author: 'k6', published_year: 2026, total_copies: 3,
    }), { headers: JSON_HEADERS, tags: { name: 'POST /books' } });
    businessConflict.add(r.status === 409);
    check(r, { 'created 201': (x) => x.status === 201 });
  }
  if (THINK) sleep(THINK);
}

export const handleSummary = makeSummary(`Scenario B - write-intensive (${__ENV.LABEL || ''})`,
  { ...META, scenario: 'B' });
