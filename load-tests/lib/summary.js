function fmt(v) {
  return v === undefined ? '-' : v >= 100 ? v.toFixed(0) : v.toFixed(1);
}

function row(name, m) {
  if (!m) return null;
  const v = m.values;
  return `${name.padEnd(48)} avg=${fmt(v.avg).padStart(7)} p50=${fmt(v.med).padStart(7)} ` +
    `p95=${fmt(v['p(95)']).padStart(7)} p99=${fmt(v['p(99)']).padStart(7)} max=${fmt(v.max).padStart(7)}`;
}

export function makeSummary(title, meta = {}) {
  return function handleSummary(data) {
    data.meta = { title, ...meta, env: { label: __ENV.LABEL || '', base_url: __ENV.BASE_URL || '' } };
    const lines = [`\n=== ${title} ===`];
    const reqs = data.metrics.http_reqs;
    const failed = data.metrics.http_req_failed;
    if (reqs) {
      lines.push(`requests: ${reqs.values.count}   throughput: ${reqs.values.rate.toFixed(1)} req/s   ` +
        `error rate: ${failed ? (failed.values.rate * 100).toFixed(2) : 0}%`);
    }
    const names = Object.keys(data.metrics).sort();
    for (const name of names) {
      const m = data.metrics[name];
      if (m.type === 'trend' && (name === 'http_req_duration' || (name.includes('{') && !name.startsWith('iteration')))) {
        lines.push(row(name, m));
      }
      if (m.type === 'counter' && name.includes('{')) {
        lines.push(`${name.padEnd(48)} count=${m.values.count}`);
      }
      if (m.type === 'rate' && name.includes('{')) {
        lines.push(`${name.padEnd(48)} rate=${(m.values.rate * 100).toFixed(2)}%`);
      }
    }
    const out = { stdout: lines.filter(Boolean).join('\n') + '\n' };
    if (__ENV.OUT) out[__ENV.OUT] = JSON.stringify(data, null, 1);
    return out;
  };
}
