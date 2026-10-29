from datetime import datetime
from uuid import UUID

from sqlalchemy import ForeignKey, func, DateTime
from sqlalchemy.orm import mapped_column, Mapped

from app.db.base import Base


class LeadDeliveryAttemptModel(Base):
    """Отметка незавершённой попытки доставки."""

    __tablename__ = "lead_delivery_attempts"

    lead_id: Mapped[UUID] = mapped_column(
        ForeignKey("leads.id", ondelete="RESTRICT"),
        primary_key=True,
    )
    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
