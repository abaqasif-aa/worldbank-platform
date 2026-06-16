# Architecture & Progress

## Overview

Open-source economic intelligence platform built on World Bank indicators
(GDP, inflation, unemployment, exports, population) for 148 countries,
2000-2023. Fully containerised with Docker Compose — designed to be cloned
and run with a single command.

## Stack

| Layer | Tool |
|---|---|
| Ingestion | Python + FastAPI |
| Storage | PostgreSQL |
| Cache | Redis |
| Transformation | dbt |
| Orchestration | Airflow (planned) |
| Vector DB | Qdrant (planned) |
| Experiment tracking | MLflow (planned) |
| Dashboards | Superset (planned) |

## Data model — medallion architecture

<!-- ![dbt lineage graph](images/dbt_lineage_graph.png) -->

## Progress

- [x] Phase 1 — Project structure
- [x] Phase 2 — Docker Compose (8 services)
- [x] Phase 3 — PostgreSQL schema
- [x] Phase 4 — Ingestion service (27,505 raw rows loaded)
- [x] Phase 5 — dbt medallion architecture (36 tests passing, snapshots, docs)
- [x] Phase 6 — Redis cache-aside layer for country metadata
- [x] Phase 7 — Airflow DAG (ingest → dbt → cache refresh, DockerOperator, daily 6am UTC)
- [x] Phase 8 — Embeddings + Qdrant (sentence-transformers, 384-dim, 3552 vectors)
- [ ] Phase 9 — RAG pipeline
- [ ] Phase 10-12 — Analytics + MLflow (regression, clustering, decision tree)
- [ ] Phase 13 — Superset dashboards
- [ ] Phase 14 — CI/CD
- [ ] ELK stack for centralised logging

## Key design decisions

- **Open source stack, deliberately**: portable across cloud providers,
  zero licence cost, full local development without cloud credentials.
- **Medallion architecture in dbt**: bronze (raw), silver (staging +
  intermediate), gold (marts) — clean separation between source-conformed
  and business-ready data.
- **Custom `generate_schema_name` macro**: overrides dbt's default
  `<target>_<custom>` schema prefixing so staging/intermediate/marts each
  get clean, dedicated schemas.
- **Three-state flags for derived columns**: e.g. `crisis_flag` can be
  `1`, `0`, or `NULL` — NULL means "insufficient data," not "no crisis."
  Avoids silently mislabeling missing data as a confirmed negative.
- **Cache-aside pattern for country metadata**: 148 rows, effectively
  static, 30-day TTL in Redis to avoid repeated Postgres lookups for
  data that essentially never changes.
- **Docker Compose `profiles`**: long-running services (Postgres, Redis,
  Airflow, etc.) start with `docker compose up`; one-off tasks (ingestion,
  dbt) use `--profile tasks run --rm` and exit after completing.
