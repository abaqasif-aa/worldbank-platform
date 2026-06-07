from fastapi import FastAPI

app = FastAPI(title="World Bank Platform API")

@app.get("/health")
def health():
    return {"status": "ok"}
