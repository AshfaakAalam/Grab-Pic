from collections.abc import Callable
from functools import lru_cache
from typing import Annotated

from fastapi import Depends, HTTPException, Path
from qdrant_client import QdrantClient
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.database import SessionLocal, get_db
from app.db.models import Event, User
from app.services.face_recognition import EMBEDDING_DIM, FaceAnalyzer
from app.services.storage import LocalStorage
from app.services.vector_store import VectorStore


def get_current_user(
    db: Session = Depends(get_db),
    settings: Settings = Depends(get_settings),
) -> User:
    """Placeholder until authentication exists.

    Returns the single default user (creating it on first use). When login is
    added later, only this function changes; every route already depends on it.
    """
    email = settings.default_user_email.strip().lower()
    user = db.scalar(select(User).where(User.email == email))
    if user is None:
        user = User(email=email)
        db.add(user)
        try:
            db.commit()
        except IntegrityError:  # another request created it first
            db.rollback()
            user = db.scalar(select(User).where(User.email == email))
    return user


def get_event_or_404(
    event_id: Annotated[int, Path(gt=0, le=2_147_483_647)],  # fits PostgreSQL INTEGER
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> Event:
    """Load an event (with photos) that belongs to the current user."""
    event = db.scalar(
        select(Event)
        .where(Event.id == event_id, Event.user_id == user.id)
        .options(selectinload(Event.photos))
    )
    if event is None:
        raise HTTPException(status_code=404, detail="Event not found.")
    return event


def get_storage(settings: Settings = Depends(get_settings)) -> LocalStorage:
    return LocalStorage(settings.upload_dir)


# --- Face search dependencies -------------------------------------------------
# lru_cache = one shared instance per process. Creating these objects does NOT
# load the model or connect to Qdrant; that happens lazily on first use.


@lru_cache
def get_face_analyzer() -> FaceAnalyzer:
    s = get_settings()
    return FaceAnalyzer(
        model_name=s.face_model_name,
        model_root=s.face_model_root,
        use_gpu=s.face_use_gpu,
        det_size=s.face_det_size,
        min_det_score=s.face_min_det_score,
        min_face_px=s.face_min_size_px,
    )


@lru_cache
def get_vector_store() -> VectorStore:
    s = get_settings()
    if s.qdrant_url:
        factory = lambda: QdrantClient(url=s.qdrant_url, api_key=s.qdrant_api_key)  # noqa: E731
    else:
        factory = lambda: QdrantClient(path=str(s.qdrant_path))  # noqa: E731
    return VectorStore(
        client_factory=factory,
        collection=s.qdrant_collection,
        vector_size=EMBEDDING_DIM,
        is_remote=bool(s.qdrant_url),
    )


def get_session_factory() -> Callable[[], Session]:
    """Background tasks run after the request, so they need their own sessions."""
    return SessionLocal