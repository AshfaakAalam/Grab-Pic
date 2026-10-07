from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.templating import templates
from app.db.database import get_db
from app.db.models import FACE_DONE, Event
from app.dependencies import (
    get_event_or_404,
    get_face_analyzer,
    get_session_factory,
    get_storage,
    get_vector_store,
)
from app.schemas.event import EventDetailResponse
from app.schemas.photo import PhotoMatchResponse, PhotoResponse
from app.services.face_pipeline import find_matching_photos, index_photos
from app.services.face_recognition import FaceAnalyzer, FaceModelUnavailable, InvalidImage
from app.services.storage import LocalStorage
from app.services.uploads import InvalidUpload, validate_image
from app.services.vector_store import VectorStore, VectorStoreError

router = APIRouter()


def _render(
    request: Request,
    event: Event,
    settings: Settings,
    *,
    results: list[PhotoMatchResponse] | None = None,
    success: str | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "find_me.html",
        {
            "event": EventDetailResponse.model_validate(event),
            "not_ready": sum(1 for p in event.photos if p.face_status != FACE_DONE),
            "results": results,  # None = nothing searched yet
            "show_scores": settings.show_match_scores,
            "success": success,
            "errors": errors or [],
        },
        status_code=status_code,
    )


@router.get("/events/{event_id}/find-me", response_class=HTMLResponse, name="find_me")
def find_me_page(
    request: Request,
    event: Event = Depends(get_event_or_404),
    settings: Settings = Depends(get_settings),
    scanning: Annotated[int, Query(ge=0, le=100000)] = 0,
):
    success = f"Scanning {scanning} photo(s) in the background. Refresh in a moment." if scanning else None
    return _render(request, event, settings, success=success)


@router.post("/events/{event_id}/find-me", name="find_me_submit")
def find_me(
    request: Request,
    reference: Annotated[UploadFile | str | None, File()] = None,
    event: Event = Depends(get_event_or_404),
    db: Session = Depends(get_db),
    analyzer: FaceAnalyzer = Depends(get_face_analyzer),
    store: VectorStore = Depends(get_vector_store),
    settings: Settings = Depends(get_settings),
):
    def fail(message: str, status_code: int = 400):
        return _render(request, event, settings, errors=[message], status_code=status_code)

    # 1. Validate the reference image (same checks as normal uploads).
    #    It is processed in memory only: never saved, never stored.
    if isinstance(reference, str) or reference is None or not reference.filename:
        return fail("Choose a photo that contains your face.")
    try:
        validate_image(reference, settings.max_upload_size_bytes)
    except InvalidUpload as exc:
        return fail(str(exc))

    # 2. Detect faces in the reference image.
    try:
        faces = analyzer.analyze(reference.file.read())
    except InvalidImage:
        return fail("This image could not be read. Please try another photo.")
    except FaceModelUnavailable:
        return fail("Face search is temporarily unavailable. Please try again later.", 503)

    if not faces:
        return fail("No face detected. Please upload a clearer photo.")
    if len(faces) > 1:
        return fail("Please upload a photo containing only your face.")

    # 3. Search this event's faces only, then load the photos from PostgreSQL.
    try:
        matches = find_matching_photos(db, event, faces[0].embedding, store, settings)
    except VectorStoreError:
        return fail("Face search is temporarily unavailable. Please try again later.", 503)

    results = [
        PhotoMatchResponse(photo=PhotoResponse.model_validate(photo), score=score)
        for photo, score in matches
    ]
    return _render(request, event, settings, results=results)


@router.post("/events/{event_id}/reindex-faces", name="reindex_faces")
def reindex_faces(
    request: Request,
    background_tasks: BackgroundTasks,
    event: Event = Depends(get_event_or_404),
    session_factory=Depends(get_session_factory),
    storage: LocalStorage = Depends(get_storage),
    analyzer: FaceAnalyzer = Depends(get_face_analyzer),
    store: VectorStore = Depends(get_vector_store),
):
    """Scan photos that are still 'pending' or 'failed' (e.g. uploaded before this
    feature existed, or when the face model / vector DB was down)."""
    ids = [p.id for p in event.photos if p.face_status != FACE_DONE]
    if ids:
        background_tasks.add_task(index_photos, ids, session_factory, storage, analyzer, store)
    url = request.url_for("find_me", event_id=event.id).include_query_params(scanning=len(ids))
    return RedirectResponse(url=url, status_code=303)