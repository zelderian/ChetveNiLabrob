# Lab 3 - results

## Scale-out (50 VUs)

| Instances | RPS | Gain | Efficiency | Avg | p50 | p95 | p99 | Errors |
|---|---|---|---|---|---|---|---|---|
| 1 | 312 | 1.00x | 100% | 159 ms | 157 ms | 285 ms | 392 ms | 0.00 % |
| 2 | 627 | 2.01x | 100% | 79 ms | 70 ms | 148 ms | 218 ms | 0.00 % |
| 3 | 597 | 1.91x | 64% | 83 ms | 60 ms | 218 ms | 370 ms | 0.00 % |

## slow_roundrobin
RPS 409, avg 73 ms, p50 5.6 ms, p95 211 ms, p99 219 ms, errors 0.00 % (12354 requests); per instance: {'app-3': 4118, 'app-1': 4117, 'app-2': 4118}

## slow_leastconn
RPS 667, avg 45 ms, p50 29 ms, p95 206 ms, p99 249 ms, errors 0.00 % (20058 requests); per instance: {'app-2': 9485, 'app-3': 1334, 'app-1': 9238}

## failover_stop
RPS 524, avg 57 ms, p50 45 ms, p95 147 ms, p99 189 ms, errors 0.00 % (13136 requests); per instance: {'app-3': 5756, 'app-2': 1623, 'app-1': 5756}

## failover_kill
RPS 507, avg 59 ms, p50 46 ms, p95 153 ms, p99 198 ms, errors 0.01 % (12692 requests); per instance: {'app-1': 5560, 'app-3': 5561, 'app-2': 1569}

## rr_baseline
RPS 546, avg 55 ms, p50 47 ms, p95 127 ms, p99 163 ms, errors 0.00 % (8226 requests); per instance: {'app-3': 2742, 'app-2': 2742, 'app-1': 2741}
