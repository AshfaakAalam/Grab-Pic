"""Thin wrapper around Qdrant. Only this file knows Qdrant exists.

Each point = one face:
    id      = face_id (UUID, same value as photo_faces.face_id in PostgreSQL)
    vector  = 512-d ArcFace embedding
    payload = {"event_id": ..., "photo_id": ..., "face_id": ...}
"""
import logging
import threading
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchValue,
    PayloadSchemaType,
    PointIdsList,
    PointStruct,
    VectorParams,
)

logger = logging.getLogger(__name__)


class VectorStoreError(Exception):
    """The vector database failed or is unreachable. Details are in the log."""


@dataclass(frozen=True)
class FaceHit:
    photo_id: int
    face_id: str
    score: float  # cosine similarity, higher = more similar


class VectorStore:
    def __init__(
        self,
        client_factory: Callable[[], QdrantClient],
        collection: str,
        vector_size: int,
        is_remote: bool,
    ):
        self._client_factory = client_factory
        self.collection = collection
        self.vector_size = vector_size
        self.is_remote = is_remote
        self._client: QdrantClient | None = None
        self._ready = False
        self._lock = threading.Lock()

    def _get_client(self) -> QdrantClient:
        """Connect and create the collection on first use (not at app startup),
        so the web app starts even when Qdrant is down."""
        with self._lock:
            if self._client is None:
                self._client = self._client_factory()
            if not self._ready:
                self._create_collection(self._client)
                self._ready = True
            return self._client

    def _create_collection(self, client: QdrantClient) -> None:
        if client.collection_exists(self.collection):
            return
        client.create_collection(
            collection_name=self.collection,
            vectors_config=VectorParams(size=self.vector_size, distance=Distance.COSINE),
        )
        if self.is_remote:  # payload indexes only matter on a real server
            client.create_payload_index(
                collection_name=self.collection,
                field_name="event_id",
                field_schema=PayloadSchemaType.INTEGER,
            )

    def insert_embeddings(self, items: list[tuple[str, np.ndarray, dict]]) -> None:
        """items = [(face_id, embedding, payload), ...]"""
        if not items:
            return
        try:
            self._get_client().upsert(
                collection_name=self.collection,
                points=[
                    PointStruct(id=face_id, vector=embedding.tolist(), payload=payload)
                    for face_id, embedding, payload in items
                ],
                wait=True,
            )
        except Exception as exc:
            logger.error("Vector store insert failed", exc_info=True)
            raise VectorStoreError("insert failed") from exc

    def search_embeddings(
        self, event_id: int, embedding: np.ndarray, limit: int, score_threshold: float
    ) -> list[FaceHit]:
        """Most similar faces, restricted to ONE event."""
        try:
            result = self._get_client().query_points(
                collection_name=self.collection,
                query=embedding.tolist(),
                query_filter=Filter(
                    must=[FieldCondition(key="event_id", match=MatchValue(value=event_id))]
                ),
                limit=limit,
                score_threshold=score_threshold,
                with_payload=["photo_id", "face_id"],
            )
        except Exception as exc:
            logger.error("Vector store search failed", exc_info=True)
            raise VectorStoreError("search failed") from exc

        return [
            FaceHit(
                photo_id=int(point.payload["photo_id"]),
                face_id=str(point.payload["face_id"]),
                score=float(point.score),
            )
            for point in result.points
        ]

    def delete_embeddings(self, face_ids: list[str]) -> None:
        if not face_ids:
            return
        try:
            self._get_client().delete(
                collection_name=self.collection,
                points_selector=PointIdsList(points=face_ids),
                wait=True,
            )
        except Exception as exc:
            logger.error("Vector store delete failed", exc_info=True)
            raise VectorStoreError("delete failed") from exc

    def count_faces(self, event_id: int | None = None) -> int:
        """Number of stored faces (optionally for one event). Handy for tests/debugging."""
        flt = None
        if event_id is not None:
            flt = Filter(must=[FieldCondition(key="event_id", match=MatchValue(value=event_id))])
        try:
            return self._get_client().count(
                collection_name=self.collection, count_filter=flt, exact=True
            ).count
        except Exception as exc:
            logger.error("Vector store count failed", exc_info=True)
            raise VectorStoreError("count failed") from exc