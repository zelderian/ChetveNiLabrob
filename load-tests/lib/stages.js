// Load profile shared by the Lab 5 scenarios.
//
// MODE=steps (default) - measurement profile:
//   warm-up (WARMUP s @ 5 VUs) followed by a series of constant-concurrency
//   steps LEVELS (default 10,25,50,100,200 VUs), each STAGE seconds long.
//   Every step is a separate k6 scenario ("vus_010", "vus_025", ...), so all
//   metrics can be reported per step (sub-metrics tagged {scenario:vus_NNN}).
// MODE=ramp - demo profile for the defence: one ramping-vus scenario that
//   climbs 0 -> 10 -> 25 -> 50 -> 100 -> 200 VUs (watch it live in the console).
//
//   k6 run -e LEVELS=10,50,100 -e STAGE=20 load-tests/scenario_a_read.js

export const LEVELS = (__ENV.LEVELS || '10,25,50,100,200').split(',').map(Number);
export const STAGE = Number(__ENV.STAGE || 30);
export const WARMUP = Number(__ENV.WARMUP || 15);
const GAP = 3; // seconds between steps: in-flight iterations of a step finish first

export function stageName(vus) {
  return `vus_${String(vus).padStart(3, '0')}`;
}

export function buildOptions(extraThresholds = {}) {
  const thresholds = { ...extraThresholds };
  const scenarios = {};

  if (__ENV.MODE === 'ramp') {
    scenarios.ramp = {
      executor: 'ramping-vus',
      startVUs: 0,
      stages: [{ duration: `${WARMUP}s`, target: 5 },
        ...LEVELS.flatMap((v) => [{ duration: '5s', target: v }, { duration: `${STAGE}s`, target: v }]),
        { duration: '5s', target: 0 }],
      gracefulRampDown: '5s',
    };
  } else {
    scenarios.warmup = {
      executor: 'constant-vus', vus: 5, duration: `${WARMUP}s`, gracefulStop: `${GAP}s`,
    };
    let start = WARMUP + GAP;
    for (const vus of LEVELS) {
      const name = stageName(vus);
      scenarios[name] = {
        executor: 'constant-vus', vus, duration: `${STAGE}s`,
        startTime: `${start}s`, gracefulStop: `${GAP}s`,
      };
      start += STAGE + GAP;
      // "always true" thresholds: force per-step sub-metrics into the summary
      thresholds[`http_req_duration{scenario:${name}}`] = ['max>=0'];
      thresholds[`http_reqs{scenario:${name}}`] = ['count>=0'];
      thresholds[`http_req_failed{scenario:${name}}`] = ['rate>=0'];
      thresholds[`iteration_duration{scenario:${name}}`] = ['max>=0'];
    }
  }

  return {
    scenarios,
    thresholds,
    summaryTrendStats: ['avg', 'min', 'med', 'p(90)', 'p(95)', 'p(99)', 'max'],
    // Load tests must not be skewed by the load generator itself:
    discardResponseBodies: false,
    noConnectionReuse: false,
    userAgent: 'libra-k6-loadtest/1.0',
    setupTimeout: '180s',
  };
}

export const META = { levels: LEVELS, stage_seconds: STAGE, warmup_seconds: WARMUP };
