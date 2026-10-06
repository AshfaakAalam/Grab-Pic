import shutil
from pathlib import Path
from typing import BinaryIO


class LocalStorage:
    """Stores files on the local disk under `base_dir`.

    The public methods (save / delete) are the only things the routes know
    about. An S3/MinIO class with the same methods can replace this later.
    """

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir.resolve()

    def _full_path(self, key: str) -> Path:
        path = (self.base_dir / key).resolve()
        if not path.is_relative_to(self.base_dir):
            raise ValueError("Invalid storage key")
        return path

    def save(self, key: str, fileobj: BinaryIO) -> None:
        path = self._full_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as out:
            shutil.copyfileobj(fileobj, out)

    def delete(self, key: str) -> None:
        try:
            self._full_path(key).unlink(missing_ok=True)
        except OSError:
            pass  # best-effort cleanup
