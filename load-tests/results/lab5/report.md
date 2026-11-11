# Lab 5 - results


## baseline / scenario_a_read

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 780 | 13 ms | 12 ms | 21 ms | 27 ms | 69 ms | 0.00 % |
| 25 | 889 | 28 ms | 27 ms | 46 ms | 57 ms | 199 ms | 0.00 % |
| 50 | 929 | 54 ms | 52 ms | 85 ms | 106 ms | 415 ms | 0.00 % |
| 100 | 883 | 113 ms | 111 ms | 180 ms | 231 ms | 495 ms | 0.00 % |
| 200 | 790 | 254 ms | 251 ms | 379 ms | 478 ms | 620 ms | 0.00 % |

## baseline / scenario_b_write

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 171 | 58 ms | 57 ms | 93 ms | 110 ms | 164 ms | 0.00 % |
| 25 | 169 | 148 ms | 147 ms | 229 ms | 268 ms | 346 ms | 0.00 % |
| 50 | 163 | 308 ms | 305 ms | 475 ms | 555 ms | 804 ms | 0.00 % |
| 100 | 149 | 683 ms | 638 ms | 1194 ms | 1553 ms | 2830 ms | 0.00 % |
| 200 | 141 | 1449 ms | 890 ms | 1939 ms | 30600 ms | 31189 ms | 0.92 % |

## baseline / scenario_c_workflow

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 136 | 73 ms | 58 ms | 211 ms | 285 ms | 483 ms | 0.00 % |
| 25 | 145 | 173 ms | 154 ms | 417 ms | 550 ms | 725 ms | 0.00 % |
| 50 | 154 | 330 ms | 306 ms | 662 ms | 965 ms | 1231 ms | 0.00 % |
| 100 | 158 | 661 ms | 629 ms | 1358 ms | 1922 ms | 2498 ms | 0.00 % |
| 200 | 118 | 1754 ms | 575 ms | 1887 ms | 31542 ms | 32150 ms | 0.90 % |

### baseline - DB / cache counters (delta per run)
```
{
 "scenario_a_read": {
  "xact_commit": 713,
  "xact_rollback": 707,
  "tup_returned": 1908716,
  "tup_fetched": 385743,
  "tup_inserted": 0,
  "tup_updated": 0,
  "blks_read": 0,
  "blks_hit": 54111,
  "cache_server_hits": 241977,
  "cache_server_misses": 34940,
  "wall_seconds": 180.9
 },
 "scenario_b_write": {
  "xact_commit": 80931,
  "xact_rollback": 27450,
  "tup_returned": 312166,
  "tup_fetched": 208196,
  "tup_inserted": 15365,
  "tup_updated": 33970,
  "blks_read": 0,
  "blks_hit": 1210841,
  "cache_server_hits": 1,
  "cache_server_misses": 1,
  "wall_seconds": 190.8
 },
 "scenario_c_workflow": {
  "xact_commit": 33461,
  "xact_rollback": 20242,
  "tup_returned": 47361690,
  "tup_fetched": 2761439,
  "tup_inserted": 3306,
  "tup_updated": 9932,
  "blks_read": 1,
  "blks_hit": 1520335,
  "wall_seconds": 194.4
 }
}
```

## no_cache / scenario_a_read

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 120 | 83 ms | 47 ms | 305 ms | 498 ms | 742 ms | 0.00 % |
| 25 | 122 | 206 ms | 168 ms | 600 ms | 902 ms | 1555 ms | 0.00 % |
| 50 | 121 | 416 ms | 396 ms | 873 ms | 1191 ms | 1910 ms | 0.00 % |
| 100 | 131 | 773 ms | 745 ms | 1419 ms | 1758 ms | 2531 ms | 0.00 % |
| 200 | 7 | 30117 ms | 30506 ms | 30989 ms | 31051 ms | 31066 ms | 59.11 % |

### no_cache - DB / cache counters (delta per run)
```
{
 "scenario_a_read": {
  "xact_commit": 17171,
  "xact_rollback": 17166,
  "tup_returned": 286532694,
  "tup_fetched": 135069772,
  "tup_inserted": 0,
  "tup_updated": 0,
  "blks_read": 0,
  "blks_hit": 10860469,
  "wall_seconds": 181.8
 }
}
```

## scale_1 / scenario_a_read

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 441 | 22 ms | 22 ms | 32 ms | 38 ms | 90 ms | 0.00 % |
| 25 | 444 | 56 ms | 55 ms | 78 ms | 96 ms | 140 ms | 0.00 % |
| 50 | 458 | 109 ms | 107 ms | 139 ms | 168 ms | 267 ms | 0.00 % |
| 100 | 459 | 218 ms | 215 ms | 271 ms | 298 ms | 345 ms | 0.00 % |
| 200 | 451 | 445 ms | 442 ms | 532 ms | 575 ms | 659 ms | 0.00 % |

### scale_1 - DB / cache counters (delta per run)
```
{
 "scenario_a_read": {
  "xact_commit": 515,
  "xact_rollback": 508,
  "tup_returned": 2422865,
  "tup_fetched": 411470,
  "tup_inserted": 0,
  "tup_updated": 0,
  "blks_read": 0,
  "blks_hit": 69021,
  "cache_server_hits": 128373,
  "cache_server_misses": 18622,
  "wall_seconds": 181.0
 }
}
```

## scale_2 / scenario_a_read

| VUs | Throughput (RPS) | Avg | p50 | p95 | p99 (tail) | Max | Error rate |
|---|---|---|---|---|---|---|---|
| 10 | 776 | 13 ms | 12 ms | 21 ms | 27 ms | 162 ms | 0.00 % |
| 25 | 760 | 33 ms | 32 ms | 51 ms | 64 ms | 545 ms | 0.00 % |
| 50 | 742 | 67 ms | 66 ms | 101 ms | 132 ms | 392 ms | 0.00 % |
| 100 | 770 | 130 ms | 128 ms | 185 ms | 222 ms | 307 ms | 0.00 % |
| 200 | 791 | 253 ms | 255 ms | 353 ms | 416 ms | 549 ms | 0.00 % |

### scale_2 - DB / cache counters (delta per run)
```
{
 "scenario_a_read": {
  "xact_commit": 621,
  "xact_rollback": 614,
  "tup_returned": 2538691,
  "tup_fetched": 506939,
  "tup_inserted": 0,
  "tup_updated": 0,
  "blks_read": 0,
  "blks_hit": 76247,
  "cache_server_hits": 219612,
  "cache_server_misses": 32256,
  "wall_seconds": 180.9
 }
}
```
