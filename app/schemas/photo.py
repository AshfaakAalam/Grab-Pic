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
    created_at: datetime
