from typing import Annotated

from fastapi import Depends, HTTPException, Path
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from app.core.config import Settings, get_settings
from app.db.database import get_db
from app.db.models import Event, User
from app.services.storage import LocalStorage


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
