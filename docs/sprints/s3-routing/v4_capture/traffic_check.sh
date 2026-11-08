#!/bin/bash
# Set 25 users, let it settle 3 min, then 5 one-minute readings of the call
# rates (2 min windows) against v3's baseline (frontend-proxy >= 2.5,
# frontend >= 4.8 calls/s) and the load generator's CPU and memory.
P=$(docker port load-generator 8089 | head -1 | awk -F: '{print $NF}')
for i in $(seq 1 12); do curl -s -m 5 -o /dev/null http://localhost:$P/ && break; sleep 5; done
curl -s -m 20 -X POST -d "user_count=25&spawn_rate=5" http://localhost:$P/swarm >/dev/null
sleep 180
q='sum by (service_name) (rate(traces_span_metrics_calls_total{span_kind=~"SPAN_KIND_SERVER|SPAN_KIND_CONSUMER",service_name=~"frontend-proxy|frontend"}[2m]))'
for i in 1 2 3 4 5; do
  r=$(curl -s -m 10 "http://localhost:9090/api/v1/query" --data-urlencode "query=$q" | jq -r '[.data.result[] | "\(.metric.service_name)=\(.value[1]|tonumber*100|round/100)"] | join(" ")')
  u=$(curl -s -m 15 http://localhost:$P/stats/requests | jq -r '"users=\(.user_count) fail/s=\(.total_fail_per_sec*100|round/100)"' 2>/dev/null)
  lg=$(docker stats --no-stream --format '{{.CPUPerc}} {{.MemUsage}}' load-generator)
  echo "$(date -u +%T) $r | ${u:-locust-timeout} | loadgen $lg"
  sleep 60
done
