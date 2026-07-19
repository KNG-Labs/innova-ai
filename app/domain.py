QUALIFICATION_FIELDS: dict[str, str] = {
    "car_model": "интересующая модель или марка авто",
    "budget": "бюджет покупки",
    "purchase_type": "способ покупки: наличные / кредит / трейд-ин",
}

REQUIRED_QUAL: tuple[str, ...] = tuple(QUALIFICATION_FIELDS)
MISSING_ALL: list[str] = [*REQUIRED_QUAL, "contact"]
EMBEDDING_DIM = 1536  # единый источник размерности для pgvector
