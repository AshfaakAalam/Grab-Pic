from collections.abc import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings

settings = get_settings()

# The engine (connection pool) is the one thing that is shared process-wide.
# Sessions are NOT shared: each request gets its own via get_db().
engine = create_engine(
    settings.database_url,
    echo=settings.sql_echo,
    pool_pre_ping=True,  # transparently replace dead pooled connections
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,  # keep objects usable after commit()
)


def get_db() -> Iterator[Session]:
    """FastAPI dependency: one session per request, always closed.

    Closing a session releases its connection and rolls back any
    transaction that was not committed.
    """
    with SessionLocal() as db:
        yield db
