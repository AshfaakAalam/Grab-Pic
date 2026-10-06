import os
from dataclasses import dataclass
from pathlib import PurePosixPath

from fastapi import UploadFile

ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
CONTENT_TYPE_EXTENSIONS = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}


class InvalidUpload(Exception):
    """Raised with a user-friendly message when a file is rejected."""


@dataclass(frozen=True)
class ValidatedImage:
    content_type: str
    extension: str
    size: int


def clean_filename(filename: str | None) -> str:
    """Display-only name: no directories, max 255 chars. Never used as a path."""
    name = PurePosixPath((filename or "").replace("\\", "/")).name
    return name[:255] or "unnamed"


def detect_content_type(header: bytes) -> str | None:
    """Identify the image type from its first bytes (magic numbers)."""
    if header.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if header.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if header[:6] in (b"GIF87a", b"GIF89a"):
        return "image/gif"
    if header[:4] == b"RIFF" and header[8:12] == b"WEBP":
        return "image/webp"
    return None


def validate_image(upload: UploadFile, max_bytes: int) -> ValidatedImage:
    name = clean_filename(upload.filename)
    allowed_msg = f"{name}: only JPG, PNG, GIF and WEBP images are allowed."

    if PurePosixPath(name).suffix.lower() not in ALLOWED_EXTENSIONS:
        raise InvalidUpload(allowed_msg)
    if upload.content_type not in CONTENT_TYPE_EXTENSIONS:
        raise InvalidUpload(allowed_msg)

    file = upload.file
    file.seek(0, os.SEEK_END)
    size = file.tell()
    file.seek(0)

    if size == 0:
        raise InvalidUpload(f"{name}: the file is empty.")
    if size > max_bytes:
        raise InvalidUpload(
            f"{name}: the file is larger than {max_bytes // (1024 * 1024)} MB."
        )

    detected = detect_content_type(file.read(12))
    file.seek(0)
    if detected is None:
        raise InvalidUpload(f"{name}: this does not look like a valid image.")

    return ValidatedImage(
        content_type=detected,
        extension=CONTENT_TYPE_EXTENSIONS[detected],
        size=size,
    )
