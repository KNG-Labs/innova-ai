from uuid import UUID

from pydantic import BaseModel, ConfigDict


class LeadDeliveryJob(BaseModel):
    """
    Единицы работы в очереди доставки.
    Сериализуются в Redis как JSON.
    """

    model_config = ConfigDict(extra="forbid")

    lead_id: UUID
    destination: str
