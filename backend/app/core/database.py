from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

from app.core.config import settings


def _normalise_url(url: str) -> str:
    # Hosted Postgres (Neon, Render) hands out postgres:// or postgresql:// URLs; point
    # SQLAlchemy at the psycopg 3 driver we install instead of the older psycopg2.
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


DATABASE_URL = _normalise_url(settings.database_url)
IS_SQLITE = DATABASE_URL.startswith("sqlite")

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if IS_SQLITE else {},
    pool_pre_ping=not IS_SQLITE,  # hosted Postgres drops idle connections
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


# Columns added after the first release. create_all() never alters existing tables, so an
# older database would be missing them; add them here instead (use Alembic if this grows).
_ADDED_COLUMNS = {
    "rooms": {"is_direct": "BOOLEAN NOT NULL DEFAULT FALSE"},
    "memberships": {"last_read_message_id": "INTEGER"},
}


def ensure_schema(bind=engine) -> None:
    Base.metadata.create_all(bind=bind)
    inspector = inspect(bind)
    with bind.begin() as conn:
        for table, columns in _ADDED_COLUMNS.items():
            existing = {c["name"] for c in inspector.get_columns(table)}
            for name, ddl in columns.items():
                if name not in existing:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
