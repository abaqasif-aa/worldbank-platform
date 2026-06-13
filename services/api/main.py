from fastapi import FastAPI, HTTPException

from cache import seed_country_cache, get_country_metadata

app = FastAPI(title="World Bank Platform API")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/cache/seed")
def cache_seed():
    count = seed_country_cache()
    return {"status": "ok", "countries_cached": count}


@app.get("/countries/{country_code}")
def country_lookup(country_code: str):
    data = get_country_metadata(country_code)
    if data is None:
        raise HTTPException(status_code=404, detail="Country not found")
    return data
