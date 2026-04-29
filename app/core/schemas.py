from pydantic import BaseModel


class MessageRequest(BaseModel):
    text: str
    session_id: str


class MessageResponse(BaseModel):
    text: str
    intent: str
