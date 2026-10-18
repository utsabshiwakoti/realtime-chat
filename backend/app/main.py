from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.auth import models as auth_models  # noqa: F401
from app.auth.router import router as auth_router
from app.core.config import settings
from app.core.database import Base, engine

from app.chat import models as chat_models
from app.chat.router import router as rooms_router

Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router)
app.include_router(rooms_router)

@app.get("/health")
def health():
    return {"status": "ok"}
