import http from 'k6/http';

export const BASE = __ENV.BASE_URL || 'http://localhost:8080';
export const JSON_HEADERS = { 'Content-Type': 'application/json' };
const PASSWORD = 'loadtest123';
const N_BOOKS = Number(__ENV.LT_BOOKS || 100);

export const SEARCH_WORDS = ['clean', 'data', 'design', 'systems', 'patterns', 'code',
  'architecture', 'distributed', 'loadtest', 'domain', 'reliable', 'scalable'];

export function memberEmail(i) {
  return `lt${i}@load.test`;
}

export function ensureBooks() {
  const reqs = [];
  for (let i = 1; i <= N_BOOKS; i++) {
    reqs.push(['POST', `${BASE}/api/v1/books`, JSON.stringify({
      isbn: `97899${String(i).padStart(8, '0')}`,
      title: `LoadTest Book ${i}`,
      author: `LoadTest Author ${i % 10}`,
      published_year: 2000 + (i % 25),
      total_copies: 1000,
    }), { headers: JSON_HEADERS, responseCallback: http.expectedStatuses(201, 409) }]);
  }
  http.batch(reqs);
  const ids = [];
  for (let offset = 0; offset < N_BOOKS; offset += 100) {
    const r = http.get(`${BASE}/api/v1/books?q=LoadTest%20Book&limit=100&offset=${offset}`);
    ids.push(...r.json('items').map((b) => b.id));
  }
  if (ids.length < N_BOOKS) throw new Error(`expected ${N_BOOKS} load-test books, got ${ids.length}`);
  return ids;
}

export function ensureMembers(n) {
  const reqs = [];
  for (let i = 1; i <= n; i++) {
    reqs.push(['POST', `${BASE}/api/v1/members`, JSON.stringify({
      full_name: `Load Tester ${i}`, email: memberEmail(i), password: PASSWORD, max_active_loans: 10,
    }), { headers: JSON_HEADERS, responseCallback: http.expectedStatuses(201, 409) }]);
  }
  for (let i = 0; i < reqs.length; i += 50) http.batch(reqs.slice(i, i + 50));
}

export function login(i, params = {}) {
  const r = http.post(`${BASE}/api/v1/auth/login`,
    JSON.stringify({ email: memberEmail(i), password: PASSWORD }),
    { headers: JSON_HEADERS, ...params });
  return r.status === 200 ? r.json('access_token') : null;
}

export function loginAll(n) {
  const tokens = [];
  for (let start = 1; start <= n; start += 20) {
    const batch = [];
    for (let i = start; i < Math.min(start + 20, n + 1); i++) {
      batch.push(['POST', `${BASE}/api/v1/auth/login`,
        JSON.stringify({ email: memberEmail(i), password: PASSWORD }), { headers: JSON_HEADERS }]);
    }
    for (const r of http.batch(batch)) tokens.push(r.json('access_token'));
  }
  return tokens;
}

export function cleanupActiveLoans(tokens) {
  for (const t of tokens) {
    const auth = { headers: { Authorization: `Bearer ${t}` } };
    const loans = http.get(`${BASE}/api/v1/me/loans?active=true`, auth).json() || [];
    for (const l of loans) http.post(`${BASE}/api/v1/loans/${l.id}/return`, null, auth);
  }
}

export function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export function uuid() {
  return 'xxxxxxxxxxxx4xxxyxxxxxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    return (c === 'x' ? r : (r & 0x3) | 0x8).toString(16);
  });
}
