from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.auth import models as auth_models  # noqa: F401  (register tables)
from app.auth.router import router as auth_router
from app.chat import models as chat_models  # noqa: F401
from app.chat.router import dm_router
from app.chat.router import router as rooms_router
from app.chat.ws import router as ws_router
from app.core.config import settings
from app.core.database import ensure_schema


@asynccontextmanager
async def lifespan(_: FastAPI):
    ensure_schema()
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(rooms_router)
app.include_router(dm_router)
app.include_router(ws_router)


@app.get("/health")
def health():
    return {"status": "ok"}


# Serve the built React app from the same origin (one URL, no CORS) when it's been built.
# Docker sets STATIC_DIR; locally it's frontend/dist after `npm run build`.
DIST = Path(settings.static_dir or Path(__file__).resolve().parents[2] / "frontend" / "dist").resolve()
if (DIST / "index.html").is_file():
    app.mount("/assets", StaticFiles(directory=DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        file = (DIST / path).resolve()
        if path and file.is_file() and DIST in file.parents:
            return FileResponse(file)
        return FileResponse(DIST / "index.html")
