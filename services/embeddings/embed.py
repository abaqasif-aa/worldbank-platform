"""
Embedding pipeline — reads marts.economic_indicators from PostgreSQL,
generates 384-dim vectors using sentence-transformers,
and upserts into Qdrant for semantic search.
"""
import os
import logging

import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct

load_dotenv()
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

COLLECTION = "economic_indicators"
VECTOR_DIM = 384
MODEL_NAME = "all-MiniLM-L6-v2"


def get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB", "worldbank"),
        user=os.getenv("POSTGRES_USER", "de"),
        password=os.getenv("POSTGRES_PASSWORD", "de"),
    )


def get_qdrant():
    return QdrantClient(
        host=os.getenv("QDRANT_HOST", "qdrant"),
        port=int(os.getenv("QDRANT_PORT", 6333)),
    )


def build_document(row: dict) -> str:
    """Convert a structured row into a rich text description for embedding.

    Every field follows 'Key: Value' format separated by pipes for
    consistency. The embedding model needs enough context to match
    natural language queries to the right records.
    """
    parts = [
        f"Country: {row['country_name']} ({row['country_code']})",
        f"Region: {row['region']}",
        f"Income group: {row['income_group']}",
        f"Year: {row['year']}",
    ]

    if row.get("gdp_usd"):
        gdp_t = row["gdp_usd"] / 1_000_000_000_000
        parts.append(f"GDP: ${gdp_t:.2f} trillion USD")

    if row.get("gdp_growth_rate") is not None:
        parts.append(f"GDP growth: {row['gdp_growth_rate']:.1f}%")

    if row.get("inflation_rate") is not None:
        parts.append(f"Inflation: {row['inflation_rate']:.1f}%")

    if row.get("unemployment_rate") is not None:
        parts.append(f"Unemployment: {row['unemployment_rate']:.1f}%")

    if row.get("exports_pct_gdp") is not None:
        parts.append(f"Exports: {row['exports_pct_gdp']:.1f}% of GDP")

    if row.get("population") is not None:
        pop_m = row["population"] / 1_000_000
        parts.append(f"Population: {pop_m:.1f} million")

    if row.get("crisis_flag") == 1:
        parts.append("Economic stress: elevated (high inflation and unemployment)")

    if row.get("is_extreme_inflation") == 1:
        parts.append("Extreme inflation detected (above 100%)")

    return " | ".join(parts)


def ensure_collection(client: QdrantClient):
    """Create the Qdrant collection if it doesn't already exist."""
    existing = [c.name for c in client.get_collections().collections]
    if COLLECTION not in existing:
        client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(
                size=VECTOR_DIM,
                distance=Distance.COSINE,
            ),
        )
        log.info(f"Created Qdrant collection: {COLLECTION}")
    else:
        log.info(f"Collection already exists: {COLLECTION}")


def run_embedding_pipeline():
    log.info("Loading embedding model...")
    model = SentenceTransformer(MODEL_NAME)

    log.info("Fetching rows from PostgreSQL...")
    conn = get_pg_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute("SELECT * FROM marts.economic_indicators")
            rows = cur.fetchall()
    finally:
        conn.close()

    log.info(f"Fetched {len(rows)} rows")

    log.info("Building document texts...")
    records = [dict(r) for r in rows]
    documents = [build_document(r) for r in records]

    # Spot check — print first document so we can verify format
    log.info(f"Sample document:\n{documents[0]}")

    log.info("Generating embeddings...")
    embeddings = model.encode(
        documents,
        batch_size=64,
        show_progress_bar=True,
    )
    log.info(f"Generated {len(embeddings)} embeddings, dim={embeddings.shape[1]}")

    log.info("Connecting to Qdrant...")
    client = get_qdrant()
    ensure_collection(client)

    log.info("Upserting vectors into Qdrant...")
    points = []
    for record, embedding, document in zip(records, embeddings, documents):
        point_id = int(hashlib.md5(f"{record['country_code']}-{record['year']}".encode()).hexdigest()[:16], 16)
        points.append(PointStruct(
            id=point_id,
            vector=embedding.tolist(),
            payload={
                "country_code":      record["country_code"],
                "country_name":      record["country_name"],
                "region":            record["region"],
                "income_group":      record["income_group"],
                "year":              record["year"],
                "gdp_usd":           record.get("gdp_usd"),
                "gdp_growth_rate":   record.get("gdp_growth_rate"),
                "inflation_rate":    record.get("inflation_rate"),
                "unemployment_rate": record.get("unemployment_rate"),
                "exports_pct_gdp":   record.get("exports_pct_gdp"),
                "population":        record.get("population"),
                "crisis_flag":       record.get("crisis_flag"),
                "text":              document,
            }
        ))

    client.upsert(collection_name=COLLECTION, points=points)
    log.info(f"Successfully upserted {len(points)} vectors into Qdrant")
    return len(points)


if __name__ == "__main__":
    count = run_embedding_pipeline()
    print(f"Done — {count} vectors in Qdrant")
