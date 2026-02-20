from fastapi import FastAPI
import uvicorn

from app.api.v1.auth import router as auth_router


app = FastAPI(title="VaultGuard API")
app.include_router(auth_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
