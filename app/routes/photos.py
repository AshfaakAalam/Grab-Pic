from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Query, Request, UploadFile
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.core.templating import templates
from app.db.database import get_db
from app.db.models import Event, Photo
from app.dependencies import get_event_or_404, get_storage
from app.schemas.event import EventDetailResponse
from app.services.storage import LocalStorage
from app.services.uploads import InvalidUpload, clean_filename, validate_image

router = APIRouter()


def _render_upload_page(
    request: Request,
    event: Event,
    *,
    success: str | None = None,
    errors: list[str] | None = None,
    status_code: int = 200,
):
    return templates.TemplateResponse(
        request,
        "upload.html",
        {
            "event": EventDetailResponse.model_validate(event),
            "success": success,
            "errors": errors or [],
        },
        status_code=status_code,
    )


@router.get("/upload/{event_id}", response_class=HTMLResponse, name="upload_photo")
def upload_page(
    request: Request,
    event: Event = Depends(get_event_or_404),
    created: Annotated[int, Query(ge=0, le=1)] = 0,
    uploaded: Annotated[int, Query(ge=0, le=1000)] = 0,
    skipped: Annotated[int, Query(ge=0, le=1000)] = 0,
):
    # Messages arrive as numeric query parameters after a redirect.
    success = None
    if uploaded:
        success = f"{uploaded} photo(s) uploaded successfully."
    elif created:
        success = "Event created. You can upload photos now."
    errors = (
        [f"{skipped} file(s) were skipped (wrong type, empty or too large)."]
        if skipped
        else []
    )
    return _render_upload_page(request, event, success=success, errors=errors)


@router.post("/upload/{event_id}", name="upload_photo_submit")
def upload_photos(
    request: Request,
    # `| str`: with no file chosen, browsers send an empty text part instead of a file.
    photos: Annotated[list[UploadFile | str] | None, File()] = None,
    event: Event = Depends(get_event_or_404),
    db: Session = Depends(get_db),
    storage: LocalStorage = Depends(get_storage),
    settings: Settings = Depends(get_settings),
):
    saved_keys: list[str] = []
    errors: list[str] = []

    try:
        for upload in photos or []:
            if isinstance(upload, str) or not upload.filename:
                continue  # nothing was chosen

            try:
                image = validate_image(upload, settings.max_upload_size_bytes)
            except InvalidUpload as exc:
                errors.append(str(exc))
                continue

            storage_key = f"events/{event.id}/photos/{uuid4()}{image.extension}"
            storage.save(storage_key, upload.file)
            saved_keys.append(storage_key)

            db.add(
                Photo(
                    event_id=event.id,
                    original_filename=clean_filename(upload.filename),
                    storage_key=storage_key,
                    content_type=image.content_type,
                    file_size=image.size,
                )
            )

        if saved_keys:
            db.commit()
    except Exception:
        # Keep files and database consistent: no row => no orphan file.
        db.rollback()
        for key in saved_keys:
            storage.delete(key)
        raise

    if saved_keys:
        url = request.url_for("upload_photo", event_id=event.id).include_query_params(
            uploaded=len(saved_keys), skipped=len(errors)
        )
        return RedirectResponse(url=url, status_code=303)

    return _render_upload_page(
        request,
        event,
        errors=errors or ["Choose at least one photo to upload."],
        status_code=400,
    )
