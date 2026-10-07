from datetime import datetime

from pydantic import BaseModel, ConfigDict


class PhotoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    event_id: int
    original_filename: str
    storage_key: str
    content_type: str
    file_size: int
    face_status: str
    created_at: datetime


class PhotoMatchResponse(BaseModel):
    """A photo returned by "Find My Photos" with its best similarity score."""

    photo: PhotoResponse
    score: float