"""Face detection + embedding, fully local (InsightFace / ONNX Runtime).

Pipeline inside FaceAnalysis.get():
    image -> SCRFD face detection -> 5-point alignment -> ArcFace embedding (512-d)

This module knows nothing about databases, HTTP or Qdrant.
Embeddings are never logged.
"""
import logging
import threading
from dataclasses import dataclass

import cv2
import numpy as np

logger = logging.getLogger(__name__)

EMBEDDING_DIM = 512  # buffalo_l / ArcFace ResNet50


class FaceModelUnavailable(Exception):
    """The model could not be loaded (not installed, download failed, ...)."""


class InvalidImage(Exception):
    """The bytes could not be decoded as an image."""


@dataclass(frozen=True)
class DetectedFace:
    embedding: np.ndarray  # float32, length 512, L2-normalised
    bbox: tuple[int, int, int, int]  # x1, y1, x2, y2
    det_score: float


def decode_image(data: bytes) -> np.ndarray:
    """Bytes -> BGR numpy array. OpenCV applies the EXIF rotation of phone photos."""
    array = np.frombuffer(data, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise InvalidImage("Could not decode the image.")
    return image


class FaceAnalyzer:
    """Lazy wrapper around InsightFace: the model loads on first use, not at startup,
    so the web app still starts even if the model is missing."""

    def __init__(
        self,
        model_name: str,
        model_root: str,
        use_gpu: bool,
        det_size: int,
        min_det_score: float,
        min_face_px: int,
    ):
        self.model_name = model_name
        self.model_root = model_root
        self.use_gpu = use_gpu
        self.det_size = det_size
        self.min_det_score = min_det_score
        self.min_face_px = min_face_px
        self._app = None
        # One inference at a time: protects GPU memory and the model object.
        self._lock = threading.Lock()

    def _load(self):
        try:
            import onnxruntime as ort
            from insightface.app import FaceAnalysis

            if hasattr(ort, "preload_dlls"):  # finds pip-installed CUDA/cuDNN libs
                try:
                    ort.preload_dlls()
                except Exception:
                    pass

            use_cuda = self.use_gpu and "CUDAExecutionProvider" in ort.get_available_providers()
            providers = (["CUDAExecutionProvider"] if use_cuda else []) + ["CPUExecutionProvider"]

            app = FaceAnalysis(
                name=self.model_name,
                root=self.model_root,
                allowed_modules=["detection", "recognition"],  # skip age/gender/landmarks
                providers=providers,
            )
            app.prepare(
                ctx_id=0 if use_cuda else -1,
                det_thresh=self.min_det_score,
                det_size=(self.det_size, self.det_size),
            )
        except Exception as exc:
            logger.error("Face model could not be loaded", exc_info=True)
            raise FaceModelUnavailable("Face model is not available.") from exc

        logger.info("Face model %s loaded on %s", self.model_name, providers[0])
        return app

    def analyze(self, image_bytes: bytes) -> list[DetectedFace]:
        """Find every usable face in an image and return one embedding per face."""
        image = decode_image(image_bytes)

        with self._lock:
            if self._app is None:
                self._app = self._load()
            raw_faces = self._app.get(image)

        faces = []
        for face in raw_faces:
            x1, y1, x2, y2 = (int(v) for v in face.bbox)
            if min(x2 - x1, y2 - y1) < self.min_face_px:
                continue  # too small to give a reliable embedding
            faces.append(
                DetectedFace(
                    embedding=np.asarray(face.normed_embedding, dtype=np.float32),
                    bbox=(x1, y1, x2, y2),
                    det_score=float(face.det_score),
                )
            )
        return faces