# Monitoring operations

## Safe checks

Use the production compose project and inspect only:

```text
docker compose ps
docker stats --no-stream
df -h
curl -fsS http://prometheus:9090/-/ready
curl -fsS http://prometheus:9090/api/v1/targets
```

Prometheus, Grafana, Alertmanager, and exporters must remain on the private
Docker network or loopback. Do not publish their ports through Nginx.

## Golden signals

Use the provisioned dashboards for traffic, error rate, latency, and
saturation. RAG panels split embedding, retrieval, BM25, hybrid, rerank, LLM,
and end-to-end durations. Provider labels are limited to Bailian, Cohere, and
DeepSeek plus stable operation/status categories.

## Maintenance

Prometheus retention is bounded by both time and size. Review TSDB growth and
filesystem headroom weekly. Do not delete the persistent monitoring volume as
part of routine maintenance. Keep the active Qdrant collection and rollback
collection unchanged while operating monitoring.
