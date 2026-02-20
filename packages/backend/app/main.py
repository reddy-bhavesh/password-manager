from fastapi import FastAPI
import uvicorn

from app.api.v1.auth import router as auth_router
from app.api.v1.vault import router as vault_router
from app.db import model_registry as _model_registry  # noqa: F401


app = FastAPI(title="VaultGuard API")
app.include_router(auth_router)
app.include_router(vault_router)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
