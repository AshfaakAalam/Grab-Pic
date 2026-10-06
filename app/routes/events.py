from typing import Annotated

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.templating import templates
from app.db.database import get_db
from app.db.models import Event, Photo, User
from app.dependencies import get_current_user
from app.schemas.event import EventCreate, EventResponse

router = APIRouter()


@router.get("/", response_class=HTMLResponse, name="home")
def home(request: Request):
    return templates.TemplateResponse(request, "index.html")


@router.get("/my-events", response_class=HTMLResponse, name="my_events")
def my_events(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # One query for events + photo counts (avoids one query per event).
    rows = db.execute(
        select(Event, func.count(Photo.id))
        .outerjoin(Photo, Photo.event_id == Event.id)
        .where(Event.user_id == user.id)
        .group_by(Event.id)
        .order_by(Event.id.desc())
    ).all()

    events = [
        EventResponse(
            id=event.id,
            name=event.name,
            created_at=event.created_at,
            photo_count=photo_count,
        )
        for event, photo_count in rows
    ]
    return templates.TemplateResponse(request, "my_events.html", {"events": events})


@router.get("/create-event", response_class=HTMLResponse, name="create_event")
def create_event_page(request: Request):
    return templates.TemplateResponse(request, "event.html")


@router.post("/create-event", name="create_event_submit")
def create_event(
    request: Request,
    event_name: Annotated[str, Form()] = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        data = EventCreate(name=event_name)
    except ValidationError:
        return templates.TemplateResponse(
            request,
            "event.html",
            {
                "errors": ["Enter an event name (1 to 100 characters)."],
                "event_name": event_name,
            },
            status_code=400,
        )

    event = Event(user_id=user.id, name=data.name)
    db.add(event)
    db.commit()  # a failure here is handled by the SQLAlchemyError handler

    url = request.url_for("upload_photo", event_id=event.id).include_query_params(
        created=1
    )
    # 303 turns the POST into a GET, so refreshing never creates a duplicate.
    return RedirectResponse(url=url, status_code=303)
