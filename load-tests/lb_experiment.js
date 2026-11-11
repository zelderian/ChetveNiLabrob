// Lab 3 - load balancing experiments through the load balancer.
// Constant concurrency; latency and hit count are broken down per instance.
//
//   k6 run load-tests/lb_experiment.js
//   k6 run -e VUS=30 -e DURATION=30s -e BASE_URL=http://localhost:8080 load-tests/lb_experiment.js
//
// Used for: algorithm comparison under a slow node (APP3_DELAY_MS=200),
// failover (stop a container during the run) and 1/2/3-instance scale-out.
import http from 'k6/http';
import { check } from 'k6';
import { Counter, Trend } from 'k6/metrics';
import { makeSummary } from './lib/summary.js';

const BASE = __ENV.BASE_URL || 'http://localhost:8080';
const INSTANCES = (__ENV.INSTANCES || 'app-1,app-2,app-3').split(',');

const hits = new Counter('instance_hits');
const latency = new Trend('instance_latency', true);

const thresholds = { http_req_failed: ['rate<0.01'] };
for (const i of INSTANCES) {
  // "always true" thresholds force k6 to report a sub-metric per instance
  thresholds[`instance_hits{instance:${i}}`] = ['count>=0'];
  thresholds[`instance_latency{instance:${i}}`] = ['max>=0'];
}

export const options = {
  scenarios: {
    load: {
      executor: 'constant-vus',
      vus: Number(__ENV.VUS || 30),
      duration: __ENV.DURATION || '30s',
    },
  },
  thresholds,
  summaryTrendStats: ['avg', 'med', 'p(95)', 'p(99)', 'max'],
};

export function setup() {
  const r = http.get(`${BASE}/api/v1/books?limit=100`);
  const ids = r.json('items').map((b) => b.id);
  if (!ids.length) throw new Error('no books - run scripts/seed.py first');
  return { ids };
}

export default function (data) {
  const id = data.ids[Math.floor(Math.random() * data.ids.length)];
  const res = http.get(`${BASE}/api/v1/books/${id}`, { tags: { name: 'GET /books/{id}' } });
  check(res, { 'status 200': (r) => r.status === 200 });
  const inst = res.headers['X-Instance-Id'] || 'none';
  hits.add(1, { instance: inst });
  latency.add(res.timings.duration, { instance: inst });
}

export const handleSummary = makeSummary(`lb_experiment (${__ENV.LABEL || 'run'})`);
