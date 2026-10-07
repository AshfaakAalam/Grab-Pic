"""Glue between PostgreSQL, the storage, the face model and the vector store.

PostgreSQL is the source of truth. Qdrant is a search index that can always
be rebuilt from the stored photos.
"""
import logging
import threading
from collections.abc import Callable
from uuid import uuid4

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.models import FACE_DONE, FACE_FAILED, Event, Photo, PhotoFace
from app.services.face_recognition import DetectedFace, FaceAnalyzer
from app.services.storage import LocalStorage
from app.services.vector_store import VectorStore

logger = logging.getLogger(__name__)

# Only one indexing job at a time in this process (one GPU, and it avoids two jobs
# processing the same photo twice).
_index_lock = threading.Lock()


def index_photos(
    photo_ids: list[int],
    session_factory: Callable[[], Session],
    storage: LocalStorage,
    analyzer: FaceAnalyzer,
    store: VectorStore,
) -> None:
    """Background job: detect faces in each photo and store their embeddings.

    Never raises: a failure marks that photo as 'failed' so it can be retried.
    """
    with _index_lock:
        for photo_id in photo_ids:
            try:
                with session_factory() as db:
                    photo = db.get(Photo, photo_id)
                    if photo is None or photo.face_status == FACE_DONE:
                        continue
                    _index_one(db, photo, storage, analyzer, store)
            except Exception:
                logger.error("Face indexing failed for photo %s", photo_id, exc_info=True)
                _mark_failed(session_factory, photo_id)


def _index_one(
    db: Session,
    photo: Photo,
    storage: LocalStorage,
    analyzer: FaceAnalyzer,
    store: VectorStore,
) -> None:
    faces: list[DetectedFace] = analyzer.analyze(storage.read(photo.storage_key))

    # Re-indexing a photo must not leave duplicate faces behind.
    old_ids = [str(i) for i in db.scalars(
        select(PhotoFace.face_id).where(PhotoFace.photo_id == photo.id)
    )]
    if old_ids:
        store.delete_embeddings(old_ids)
        db.execute(delete(PhotoFace).where(PhotoFace.photo_id == photo.id))

    new_faces = [(uuid4(), face) for face in faces]

    # 1) vectors first ...
    store.insert_embeddings([
        (
            str(face_id),
            face.embedding,
            {"event_id": photo.event_id, "photo_id": photo.id, "face_id": str(face_id)},
        )
        for face_id, face in new_faces
    ])

    # 2) ... then the PostgreSQL rows. If this fails, undo step 1.
    try:
        db.add_all([PhotoFace(photo_id=photo.id, face_id=face_id) for face_id, _ in new_faces])
        photo.face_status = FACE_DONE
        db.commit()
    except Exception:
        db.rollback()
        store.delete_embeddings([str(face_id) for face_id, _ in new_faces])
        raise


def _mark_failed(session_factory: Callable[[], Session], photo_id: int) -> None:
    try:
        with session_factory() as db:
            photo = db.get(Photo, photo_id)
            if photo is not None:
                photo.face_status = FACE_FAILED
                db.commit()
    except Exception:
        logger.error("Could not mark photo %s as failed", photo_id, exc_info=True)


def find_matching_photos(
    db: Session,
    event: Event,
    query_embedding,
    store: VectorStore,
    settings: Settings,
) -> list[tuple[Photo, float]]:
    """Photos of `event` that contain a face similar to `query_embedding`,
    best match first. Each photo appears once."""
    hits = store.search_embeddings(
        event_id=event.id,
        embedding=query_embedding,
        limit=settings.face_search_limit,
        score_threshold=settings.face_match_threshold,
    )

    best_score: dict[int, float] = {}  # a photo may have several matching faces
    for hit in hits:
        best_score[hit.photo_id] = max(hit.score, best_score.get(hit.photo_id, -1.0))
    if not best_score:
        return []

    # Re-check against PostgreSQL: photo must exist AND belong to this event.
    photos = db.scalars(
        select(Photo).where(Photo.id.in_(list(best_score)), Photo.event_id == event.id)
    ).all()
    return sorted(((p, best_score[p.id]) for p in photos), key=lambda x: x[1], reverse=True)