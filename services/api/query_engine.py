"""
Query engine — routes questions to SQL, semantic search, or hybrid,
extracts filters from natural language, and builds safe SQL queries.
"""
import os
import json
import logging

import psycopg2
from psycopg2.extras import RealDictCursor
from openai import OpenAI

log = logging.getLogger(__name__)


def get_llm_client() -> OpenAI:
    return OpenAI(
        base_url=os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434/v1"),
        api_key="ollama",
    )


def get_pg_conn():
    return psycopg2.connect(
        host=os.getenv("POSTGRES_HOST", "postgres"),
        port=os.getenv("POSTGRES_PORT", 5432),
        dbname=os.getenv("POSTGRES_DB", "worldbank"),
        user=os.getenv("POSTGRES_USER", "de"),
        password=os.getenv("POSTGRES_PASSWORD", "de"),
    )


# ── Step 1: Classify question ─────────────────────────────────────────────────
def classify_question(question: str) -> str:
    prompt = """You are a query router for an economic data platform.

IMPORTANT CONTEXT: This database contains World Bank economic data for 148 countries covering years 2000-2023 ONLY. No data exists for 2024 or beyond.

Classify the question as:
- SQL: asks for specific data with numerical filters, thresholds, years, rankings, or counts
- SEMANTIC: asks for explanation, analysis, trends, comparisons, or narratives only
- HYBRID: asks for BOTH specific data AND explanation/analysis
- OUT_OF_RANGE: asks for data from years before 2000 or after 2023

Examples of SQL questions:
- "Which countries had inflation above 10% in 2022?"
- "Top 5 countries by unemployment in 2023?"
- "What was Brazil's GDP in 2020?"

Examples of SEMANTIC questions:
- "Explain the economic situation in Lebanon"
- "Why did Turkey's inflation rise so dramatically?"
- "Which countries have similar economic patterns to Brazil?"

Examples of HYBRID questions:
- "Which countries had the highest inflation in 2022 and why?"
- "Show me countries with crisis_flag in 2023 and explain what caused it"
- "What were the top economies in Sub-Saharan Africa in 2020 and how did they get there?"

Examples of OUT_OF_RANGE questions:
- "Which countries had the highest inflation in 2025?"
- "Show me unemployment data for 1995"

Respond with ONLY one word: SQL, SEMANTIC, HYBRID, or OUT_OF_RANGE

Question: """ + question

    response = get_llm_client().chat.completions.create(
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:latest"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    classification = response.choices[0].message.content.strip().upper()

    if "OUT_OF_RANGE" in classification:
        return "OUT_OF_RANGE"
    if "HYBRID" in classification:
        return "HYBRID"
    if "SQL" in classification:
        return "SQL"
    return "SEMANTIC"


# ── Step 2: Extract filters ───────────────────────────────────────────────────
def extract_filters(question: str) -> dict:
    prompt = """You are a filter extractor for an economic database.

IMPORTANT: This database covers years 2000-2023 only.

Extract filters from the question and return ONLY a valid JSON object.
No explanation, no markdown, no thinking, just the JSON.

Available filters:
- year: integer (e.g. 2022) or null
- year_from: integer for range start or null
- year_to: integer for range end or null
- country_code: 3-letter code (e.g. "BRA") or null
- country_name: full name (e.g. "Brazil") or null
- region: one of ["Sub-Saharan Africa", "Europe & Central Asia", "Latin America & Caribbean", "Middle East & North Africa", "North America", "South Asia", "East Asia & Pacific"] or null
- income_group: one of ["Low income", "Lower middle income", "Upper middle income", "High income"] or null
- indicator: one of ["inflation_rate", "gdp_usd", "gdp_growth_rate", "unemployment_rate", "exports_pct_gdp", "population"] or null
- operator: one of [">", "<", ">=", "<=", "="] or null
- threshold: numeric value or null
- crisis_flag: 1 or null
- order_by: column name or null
- order_dir: "DESC" or "ASC" or null
- limit: integer (default 20) or null

Example:
Question: "Which countries had inflation above 10% in 2022?"
JSON: {"year": 2022, "year_from": null, "year_to": null, "country_code": null, "country_name": null, "region": null, "income_group": null, "indicator": "inflation_rate", "operator": ">", "threshold": 10, "crisis_flag": null, "order_by": "inflation_rate", "order_dir": "DESC", "limit": 10}

Question: """ + question + """
JSON:"""

    response = get_llm_client().chat.completions.create(
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:latest"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
    )

    raw = response.choices[0].message.content.strip()

    if "```" in raw:
        raw = raw.split("```")[1]
        if raw.startswith("json"):
            raw = raw[4:]

    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        log.warning(f"Failed to parse filters JSON: {raw}")
        return {}


# ── Step 3: Build safe SQL ────────────────────────────────────────────────────
def build_sql(filters: dict) -> tuple[str, list]:
    select = """
        SELECT
            country_name, country_code, region, income_group, year,
            gdp_usd, gdp_growth_rate, inflation_rate,
            unemployment_rate, exports_pct_gdp, population,
            crisis_flag
        FROM marts.economic_indicators
    """

    conditions = []
    params = []

    if filters.get("year"):
        conditions.append("year = %s")
        params.append(filters["year"])

    if filters.get("year_from"):
        conditions.append("year >= %s")
        params.append(filters["year_from"])

    if filters.get("year_to"):
        conditions.append("year <= %s")
        params.append(filters["year_to"])

    if filters.get("country_code"):
        conditions.append("country_code = %s")
        params.append(filters["country_code"].upper())

    if filters.get("country_name"):
        conditions.append("LOWER(country_name) = LOWER(%s)")
        params.append(filters["country_name"])

    if filters.get("region"):
        conditions.append("region = %s")
        params.append(filters["region"])

    if filters.get("income_group"):
        conditions.append("income_group = %s")
        params.append(filters["income_group"])

    if filters.get("crisis_flag"):
        conditions.append("crisis_flag = %s")
        params.append(filters["crisis_flag"])

    SAFE_INDICATORS = {
        "inflation_rate", "gdp_usd", "gdp_growth_rate",
        "unemployment_rate", "exports_pct_gdp", "population"
    }
    SAFE_OPERATORS = {">", "<", ">=", "<=", "="}

    if filters.get("indicator") and filters.get("operator") and filters.get("threshold") is not None:
        indicator = filters["indicator"]
        operator  = filters["operator"]
        if indicator in SAFE_INDICATORS and operator in SAFE_OPERATORS:
            conditions.append(f"{indicator} {operator} %s")
            params.append(filters["threshold"])

    where = ""
    if conditions:
        where = "WHERE " + " AND ".join(conditions)

    SAFE_COLUMNS = SAFE_INDICATORS | {"year", "country_name", "country_code", "region"}
    order = ""
    if filters.get("order_by") and filters["order_by"] in SAFE_COLUMNS:
        direction = "DESC" if filters.get("order_dir", "DESC") == "DESC" else "ASC"
        order = f"ORDER BY {filters['order_by']} {direction}"

    limit_val = filters.get('limit') or 20
    limit = f"LIMIT {int(limit_val)}"

    sql = f"{select} {where} {order} {limit}"
    return sql, params


# ── Step 4: Execute query ─────────────────────────────────────────────────────
def execute_query(sql: str, params: list) -> list[dict]:
    conn = get_pg_conn()
    try:
        with conn.cursor(cursor_factory=RealDictCursor) as cur:
            cur.execute(sql, params)
            rows = cur.fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


# ── Step 5: Format results ────────────────────────────────────────────────────
def format_results_as_context(rows: list[dict]) -> str:
    if not rows:
        return "No data found matching the query."

    lines = []
    for r in rows:
        parts = [
            f"Country: {r.get('country_name')} ({r.get('country_code')})",
            f"Region: {r.get('region')}",
            f"Year: {r.get('year')}",
        ]
        if r.get("inflation_rate") is not None:
            parts.append(f"Inflation: {r['inflation_rate']:.1f}%")
        if r.get("gdp_growth_rate") is not None:
            parts.append(f"GDP growth: {r['gdp_growth_rate']:.1f}%")
        if r.get("unemployment_rate") is not None:
            parts.append(f"Unemployment: {r['unemployment_rate']:.1f}%")
        if r.get("gdp_usd") is not None:
            parts.append(f"GDP: ${float(r['gdp_usd'])/1e12:.2f}T")
        if r.get("crisis_flag") == 1:
            parts.append("Crisis flag: YES")
        lines.append(" | ".join(parts))

    return "\n".join(lines)


# ── SQL route ─────────────────────────────────────────────────────────────────
def sql_query(question: str) -> dict:
    log.info(f"SQL route for: {question}")

    filters = extract_filters(question)
    log.info(f"Extracted filters: {filters}")

    sql, params = build_sql(filters)
    log.info(f"Built SQL: {sql}")

    rows = execute_query(sql, params)
    log.info(f"Query returned {len(rows)} rows")

    context = format_results_as_context(rows)

    if not rows:
        return {
            "answer": "No data found matching your query criteria.",
            "sources": [],
            "context_records": 0,
            "route": "SQL",
        }

    prompt = f"""You are an economic research assistant. Answer the question using ONLY the data below.
List ALL countries in the data — do not stop early or truncate the list.
Be specific — cite country names, country codes, and exact figures for every entry.
Format as a numbered list. Do not add any commentary beyond what the data shows.

DATA:
{context}

QUESTION: {question}

ANSWER:"""

    response = get_llm_client().chat.completions.create(
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:latest"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer":          answer,
        "sources":         [{"country": r.get("country_name"), "year": r.get("year")} for r in rows],
        "context_records": len(rows),
        "route":           "SQL",
    }


# ── Hybrid route ──────────────────────────────────────────────────────────────
def hybrid_query(question: str, rag_query_fn) -> dict:
    """
    Runs both SQL and semantic search, combines context,
    generates a single unified answer.
    """
    log.info(f"HYBRID route for: {question}")

    # SQL path
    filters = extract_filters(question)
    sql, params = build_sql(filters)
    rows = execute_query(sql, params)
    sql_context = format_results_as_context(rows)

    # Semantic path — get raw answer from RAG
    semantic_result = rag_query_fn(question, top_k=5)

    # Combine both contexts
    combined_context = f"""PRECISE DATA (from database query):
{sql_context}

ADDITIONAL CONTEXT (from semantic search):
{semantic_result.get('answer', '')}"""

    prompt = f"""You are an economic research assistant. Answer the question using the data provided below.
Use the PRECISE DATA for specific figures and the ADDITIONAL CONTEXT for broader analysis.
Be specific — cite country names, years, and figures. Keep your answer concise. Do not show your thinking.

{combined_context}

QUESTION: {question}

ANSWER:"""

    response = get_llm_client().chat.completions.create(
        model=os.getenv("OLLAMA_MODEL", "qwen3.5:latest"),
        messages=[{"role": "user", "content": prompt}],
        temperature=0.1,
    )

    answer = response.choices[0].message.content.strip()

    return {
        "answer":          answer,
        "sources":         [{"country": r.get("country_name"), "year": r.get("year")} for r in rows],
        "context_records": len(rows),
        "route":           "HYBRID",
    }
