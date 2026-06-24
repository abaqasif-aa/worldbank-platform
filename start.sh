#!/bin/bash
set -e

echo "Starting World Bank Platform..."

echo "Step 1: Starting foundation services (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant

echo "Waiting for postgres to be healthy..."
until docker compose exec postgres pg_isready -U de > /dev/null 2>&1; do
    sleep 2
done
echo "Postgres is ready."

echo "Step 2: Starting application services (mlflow, airflow, superset)..."
docker compose up -d mlflow airflow superset

echo "Step 3: Starting API service..."
docker compose up -d api

echo "Step 4: Starting Jupyter..."
docker compose up -d jupyter

echo "Step 5: Starting Streamlit..."
docker compose up -d streamlit

echo "Waiting for services to be ready..."
sleep 10

echo "Opening browser tabs..."
cmd.exe /c start http://localhost:8000/docs
cmd.exe /c start http://localhost:8080
cmd.exe /c start http://localhost:5000
cmd.exe /c start http://localhost:8088
cmd.exe /c start http://localhost:8888
cmd.exe /c start http://localhost:8501

echo ""
echo "Platform is up. Services available at:"
echo "  API:      http://localhost:8000/docs"
echo "  Airflow:  http://localhost:8080"
echo "  MLflow:   http://localhost:5000"
echo "  Superset: http://localhost:8088"
echo "  Jupyter:  http://localhost:8888"
echo "  Streamlit: http://localhost:8501"
