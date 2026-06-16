"""
World Bank Economic Intelligence Platform — Daily Pipeline DAG

Schedule: 6am UTC daily
Tasks:
  1. ingest     → pull World Bank API, load to PostgreSQL
  2. dbt_build  → transform + test (staging → intermediate → marts)
  3. seed_cache → refresh Redis country metadata cache
"""
from datetime import datetime, timedelta

from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.providers.docker.operators.docker import DockerOperator
from docker.types import Mount

import requests
import os

# ── Default args ──────────────────────────────────────────────────────────────
default_args = {
    "owner": "worldbank",
    "retries": 2,
    "retry_delay": timedelta(minutes=5),
    "email_on_failure": False,
}

# ── Shared Docker config ───────────────────────────────────────────────────────
NETWORK = "worldbank_default"

ENV_FILE = "/opt/airflow/.env"

def load_env_vars() -> dict:
    """Read .env file into a dict for passing to Docker containers."""
    env = {}
    if os.path.exists(ENV_FILE):
        with open(ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    env[key.strip()] = value.strip()
    return env

# ── Seed cache task (Python, calls FastAPI endpoint) ─────────────────────────
def seed_redis_cache():
    """Call the FastAPI /cache/seed endpoint to refresh Redis."""
    api_url = "http://api:8000/cache/seed"
    resp = requests.post(api_url, timeout=30)
    resp.raise_for_status()
    result = resp.json()
    print(f"Cache seeded: {result}")
    return result


# ── DAG definition ────────────────────────────────────────────────────────────
with DAG(
    dag_id="worldbank_pipeline",
    description="Daily ingestion, dbt transformation, and cache refresh",
    schedule_interval="0 6 * * *",
    start_date=datetime(2024, 1, 1),
    catchup=False,
    default_args=default_args,
    tags=["worldbank", "production"],
) as dag:

    # Task 1 — Ingestion
    ingest = DockerOperator(
        task_id="ingest",
        image="worldbank-ingestion:latest",
        container_name="airflow_ingestion_run",
        network_mode=NETWORK,
        environment=load_env_vars(),
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        mounts=[
            Mount(
                source="/mnt/d/PractiseProjects/WorldBank/data",
                target="/app/data",
                type="bind",
            )
        ],
    )

    # Task 2 — dbt build (runs seed + models + tests)
    dbt_build = DockerOperator(
        task_id="dbt_build",
        image="worldbank-dbt:latest",
        container_name="airflow_dbt_run",
        network_mode=NETWORK,
        environment=load_env_vars(),
        auto_remove=True,
        docker_url="unix://var/run/docker.sock",
        command="build --project-dir /dbt/worldbank_dbt --profiles-dir /dbt",
    )

    # Task 3 — Seed Redis cache
    seed_cache = PythonOperator(
        task_id="seed_cache",
        python_callable=seed_redis_cache,
    )

    # ── Dependencies ──────────────────────────────────────────────────────────
    ingest >> dbt_build >> seed_cache

