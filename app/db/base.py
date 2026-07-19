from datetime import datetime

from sqlalchemy import DateTime
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Базовый класс для всех моделей SQLAlchemy."""

    pass


class SoftDeleteMixin:
    """
    Мягкое удаление: помечаем deleted_at вместо физического DELETE.

    ВАЖНО: все запросы на чтение обязаны фильтровать deleted_at IS NULL.
    """

    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        default=None,
    )
