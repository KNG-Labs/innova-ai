from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import UniqueConstraint, String, DateTime, func
from sqlalchemy.orm import mapped_column, Mapped, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.dialog_session_model import DialogSession


class User(Base):
    """
    Модель Юзера, пользователя нашего продукта

    На текущем этапе пользователь может быть анонимным.
    Anonymous_id приходит от клиента: website / telegram / avito
    """

    __tablename__ = "users"
    __table_args__ = (
        UniqueConstraint(
            "channel",
            "anonymous_id",
            name="uq_users_channel_anonymous_id",
        ),
    )

    id: Mapped[UUID] = mapped_column(
        primary_key=True,
        default=uuid4,
    )

    anonymous_id: Mapped[str] = mapped_column(
        String(128),
        nullable=False,
    )

    channel: Mapped[str] = mapped_column(
        String(32),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    session: Mapped[list[DialogSession]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
    )
