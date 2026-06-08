import requests
import json
import logging
import os
from pathlib import Path
from datetime import date

import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s"
)
log = logging.getLogger(__name__)

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL = os.getenv("WB_BASE_URL", "https://api.worldbank.org/v2")
RAW_DIR  = Path(os.getenv("RAW_DIR", "data/raw"))
START    = int(os.getenv("WB_START_YEAR", 2000))
END      = int(os.getenv("WB_END_YEAR", 2023))

INDICATORS = {
    "NY.GDP.MKTP.CD": "gdp_usd",
    "FP.CPI.TOTL.ZG": "inflation_rate",
    "SL.UEM.TOTL.ZS": "unemployment_rate",
    "NE.EXP.GNFS.ZS": "exports_pct_gdp",
    "SP.POP.TOTL":    "population",
}

# ── Database ─────────────────────────────────────────────────────────────────
def get_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB", "worldbank"),
        user=os.getenv("POSTGRES_USER", "de"),
        password=os.getenv("POSTGRES_PASSWORD", "de"),
    )

# ── Fetch ─────────────────────────────────────────────────────────────────────
def fetch_indicator(code: str, name: str) -> list:
    all_records = []
    page = 1

    while True:
        url = f"{BASE_URL}/country/all/indicator/{code}"
        params = {
            "format":   "json",
            "per_page": 1000,
            "page":     page,
            "date":     f"{START}:{END}",
        }

        log.info(f"Fetching {name} page {page}...")
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()

        meta, data = resp.json()

        if not data:
            break

        all_records.extend(data)
        log.info(f"{name} page {page}/{meta['pages']} — {len(data)} records")

        if page >= meta["pages"]:
            break

        page += 1

    return all_records

# ── Save Raw ──────────────────────────────────────────────────────────────────
def save_raw(name: str, records: list) -> Path:
    out = RAW_DIR / name / f"{date.today()}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(records, indent=2))
    log.info(f"Saved {len(records)} records to {out}")
    return out

# ── Load ──────────────────────────────────────────────────────────────────────
def load_to_postgres(code: str, name: str, records: list) -> int:
    rows = []

    for r in records:
        if r.get("value") is None:
            continue

        country = r.get("countryiso3code") or ""
        if not country or len(country) != 3:
            continue

        rows.append((
            country.upper(),
            code,
            name,
            int(r["date"]),
            float(r["value"]),
        ))

    if not rows:
        log.warning(f"No valid rows to insert for {name}")
        return 0

    sql = """
        INSERT INTO raw.indicator_records
            (country_code, indicator_code, indicator_name, year, value)
        VALUES %s
        ON CONFLICT (country_code, indicator_code, year)
        DO UPDATE SET
            value = EXCLUDED.value,
            ingested_at = NOW()
    """

    conn = get_conn()
    try:
        with conn.cursor() as cur:
            execute_values(cur, sql, rows)
        conn.commit()
        log.info(f"Upserted {len(rows)} rows for {name}")
        return len(rows)
    finally:
        conn.close()

# ── Main ──────────────────────────────────────────────────────────────────────
def run_ingestion() -> dict:
    results = {}

    for code, name in INDICATORS.items():
        log.info(f"Starting ingestion for {name}...")
        try:
            records = fetch_indicator(code, name)
            save_raw(name, records)
            n = load_to_postgres(code, name, records)
            results[name] = {
                "records_fetched": len(records),
                "rows_loaded": n,
                "status": "success"
            }
        except Exception as e:
            log.error(f"Failed to ingest {name}: {e}")
            results[name] = {
                "status": "failed",
                "error": str(e)
            }

    return results


if __name__ == "__main__":
    results = run_ingestion()
    print(json.dumps(results, indent=2))
