from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.schemas.photo import PhotoResponse

EventName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)
]


class EventCreate(BaseModel):
    name: EventName


class EventResponse(BaseModel):
    """Event as shown in a list (includes a photo count)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    photo_count: int = 0


class EventDetailResponse(BaseModel):
    """A single event with its photos."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    created_at: datetime
    photos: list[PhotoResponse] = []
