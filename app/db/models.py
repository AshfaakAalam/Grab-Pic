import uuid
from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    MetaData,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

# Explicit constraint names make Alembic migrations deterministic and
# make it possible to drop/alter constraints by name later.
NAMING_CONVENTION = {
    "ix": "ix_%(column_0_label)s",
    "uq": "uq_%(table_name)s_%(column_0_name)s",
    "ck": "ck_%(table_name)s_%(constraint_name)s",
    "fk": "fk_%(table_name)s_%(column_0_name)s_%(referred_table_name)s",
    "pk": "pk_%(table_name)s",
}


# Values for Photo.face_status
FACE_PENDING = "pending"  # uploaded, faces not scanned yet
FACE_DONE = "done"        # scanned (0 faces is still "done")
FACE_FAILED = "failed"    # scanning failed, can be retried


class Base(DeclarativeBase):
    metadata = MetaData(naming_convention=NAMING_CONVENTION)


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    # onupdate is applied by SQLAlchemy on ORM UPDATEs (not by the database).
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    # unique=True creates a unique index, so no separate index is needed.
    email: Mapped[str] = mapped_column(String(320), unique=True)

    events: Mapped[list["Event"]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        passive_deletes=True,  # let PostgreSQL's ON DELETE CASCADE do the work
    )


class Event(TimestampMixin, Base):
    __tablename__ = "events"
    __table_args__ = (
        CheckConstraint("length(trim(name)) > 0", name="name_not_blank"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed because "all events of this user" is the main query.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(100))

    user: Mapped["User"] = relationship(back_populates="events")
    photos: Mapped[list["Photo"]] = relationship(
        back_populates="event",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="Photo.id",
    )


class Photo(TimestampMixin, Base):
    __tablename__ = "photos"
    __table_args__ = (
        CheckConstraint("file_size > 0", name="file_size_positive"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    # Indexed because the gallery loads "all photos of this event".
    event_id: Mapped[int] = mapped_column(
        ForeignKey("events.id", ondelete="CASCADE"), index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255))
    # Location of the bytes in whatever storage backend is used
    # (local path today, S3/MinIO object key later). Unique per object.
    storage_key: Mapped[str] = mapped_column(String(512), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    file_size: Mapped[int] = mapped_column(BigInteger)
    # Where this photo is in the face-scanning pipeline (see FACE_* constants).
    face_status: Mapped[str] = mapped_column(
        String(20), default=FACE_PENDING, server_default=FACE_PENDING
    )

    event: Mapped["Event"] = relationship(back_populates="photos")
    faces: Mapped[list["PhotoFace"]] = relationship(
        back_populates="photo",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class PhotoFace(Base):
    """One detected face in one photo.

    The embedding itself lives in the vector database. `face_id` is the ID of
    that vector (Qdrant point ID), so the two stores are linked by a stable ID.
    """

    __tablename__ = "photo_faces"

    id: Mapped[int] = mapped_column(primary_key=True)
    photo_id: Mapped[int] = mapped_column(
        ForeignKey("photos.id", ondelete="CASCADE"), index=True
    )
    face_id: Mapped[uuid.UUID] = mapped_column(Uuid, unique=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    photo: Mapped["Photo"] = relationship(back_populates="faces")