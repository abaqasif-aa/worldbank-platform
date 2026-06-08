#!/bin/bash
set -e

echo "Running Airflow DB migration..."
airflow db migrate

echo "Creating admin user..."
airflow users create \
    --username admin \
    --password admin \
    --firstname Admin \
    --lastname Admin \
    --role Admin \
    --email admin@example.com 2>/dev/null || true

echo "Starting Airflow webserver and scheduler..."
airflow webserver &
airflow scheduler
