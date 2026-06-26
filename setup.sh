#!/bin/bash
set -e

echo "========================================"
echo " World Bank Economic Intelligence Setup"
echo "========================================"

# ── Detect OS ─────────────────────────────────────────────────────────────────
if grep -qi microsoft /proc/version 2>/dev/null; then
    OS="windows"
    OLLAMA_HOST="host.docker.internal"
    OPEN_CMD="cmd.exe /c start"
    echo "Detected: Windows (WSL2)"
else
    OS="linux"
    OLLAMA_HOST="localhost"
    if command -v xdg-open &> /dev/null; then
        OPEN_CMD="xdg-open"
    elif command -v open &> /dev/null; then
        OPEN_CMD="open"
    else
        OPEN_CMD=""
    fi
    echo "Detected: Linux/Mac"
fi

# ── Step 1: Check prerequisites ───────────────────────────────────────────────
echo ""
echo "Step 1: Checking prerequisites..."

if ! command -v docker &> /dev/null; then
    echo "ERROR: Docker not found. Install Docker Desktop from https://docker.com"
    exit 1
fi

if ! docker compose version &> /dev/null; then
    echo "ERROR: Docker Compose not found. Install Docker Desktop from https://docker.com"
    exit 1
fi

echo "✓ Docker found"

# ── Step 2: Setup .env ────────────────────────────────────────────────────────
echo ""
echo "Step 2: Setting up environment..."

if [ ! -f .env ]; then
    cp .env.example .env
    # Update Ollama host based on detected OS
    sed -i "s|OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://${OLLAMA_HOST}:11434/v1|" .env
    echo "✓ Created .env from .env.example"
    echo "  Review .env and update MLFLOW_TRACKING_USERNAME if needed"
else
    echo "✓ .env already exists — skipping"
fi

# ── Step 3: Build images ──────────────────────────────────────────────────────
echo ""
echo "Step 3: Building Docker images (this may take 5-10 minutes)..."
docker compose build
echo "✓ All images built"

# ── Step 4: Start foundation services ─────────────────────────────────────────
echo ""
echo "Step 4: Starting foundation services (postgres, redis, qdrant)..."
docker compose up -d postgres redis qdrant

echo "Waiting for PostgreSQL to be ready..."
until docker compose exec postgres pg_isready -U de > /dev/null 2>&1; do
    sleep 2
done
echo "✓ PostgreSQL ready"

# ── Step 5: Run ingestion ─────────────────────────────────────────────────────
echo ""
echo "Step 5: Loading World Bank data (this may take 2-3 minutes)..."
docker compose --profile tasks run --rm ingestion
echo "✓ Data loaded"

# ── Step 6: Run dbt ───────────────────────────────────────────────────────────
echo ""
echo "Step 6: Building dbt medallion architecture..."
docker compose --profile tasks run --rm dbt build \
    --project-dir /dbt/worldbank_dbt \
    --profiles-dir /dbt
echo "✓ dbt models built (36 tests passing)"

# ── Step 7: Start remaining services ─────────────────────────────────────────
echo ""
echo "Step 7: Starting application services..."
docker compose up -d mlflow airflow api jupyter streamlit
echo "Waiting for services to initialise..."
sleep 15
echo "✓ All services running"

# ── Step 8: Seed Redis cache ──────────────────────────────────────────────────
echo ""
echo "Step 8: Seeding Redis country metadata cache..."
until curl -s http://localhost:8000/health > /dev/null 2>&1; do
    sleep 3
done
curl -s -X POST http://localhost:8000/cache/seed > /dev/null
echo "✓ Redis cache seeded"

# ── Step 9: Generate embeddings ───────────────────────────────────────────────
echo ""
echo "Step 9: Generating Qdrant embeddings (this may take 2-3 minutes)..."
docker compose --profile tasks run --rm embeddings
echo "✓ Embeddings generated (3,552 vectors)"

# ── Done ──────────────────────────────────────────────────────────────────────
echo ""
echo "========================================"
echo " Setup complete!"
echo "========================================"
echo ""
echo "Services available at:"
echo "  Chat interface : http://localhost:8501"
echo "  API docs       : http://localhost:8000/docs"
echo "  Airflow        : http://localhost:8080  (admin/admin)"
echo "  MLflow         : http://localhost:5000"
echo "  Jupyter        : http://localhost:8888"
echo ""
echo "IMPORTANT — Local LLM setup (required for RAG):"
echo "  1. Install Ollama from https://ollama.com"
echo "  2. Pull the model:"
echo "     ollama pull llama3.1:8b-instruct-q4_0"

if [ "$OS" = "windows" ]; then
echo ""
echo "  3. Windows: Set OLLAMA_HOST=0.0.0.0 in System Environment Variables"
echo "     then restart Ollama from the Start menu."
echo "     Or in Command Prompt: set OLLAMA_HOST=0.0.0.0 && ollama serve"
else
echo ""
echo "  3. Linux/Mac: Run: OLLAMA_HOST=0.0.0.0 ollama serve"
fi

echo ""
echo "The RAG pipeline will work once Ollama is running with OLLAMA_HOST=0.0.0.0"
echo "========================================"
