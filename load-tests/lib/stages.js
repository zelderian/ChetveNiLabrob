export const LEVELS = (__ENV.LEVELS || '10,25,50,100,200').split(',').map(Number);
export const STAGE = Number(__ENV.STAGE || 30);
export const WARMUP = Number(__ENV.WARMUP || 15);
const GAP = 3;

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
    discardResponseBodies: false,
    noConnectionReuse: false,
    userAgent: 'libra-k6-loadtest/1.0',
    setupTimeout: '180s',
  };
}

export const META = { levels: LEVELS, stage_seconds: STAGE, warmup_seconds: WARMUP };
