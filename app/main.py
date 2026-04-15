from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class MessageRequest(BaseModel):
    text: str
    session_id: str
    
class MessageResponse(BaseModel):
    text: str
    intent: str   # о чем спрашивал пользователь, тематика 
    
    
def llm_sub(text: str) -> MessageResponse:
    return MessageResponse(
        text='Здравствуйте! Чем могу помочь?',
        intent='greeting'
    )
    
@app.post('/message', response_model=MessageResponse)
def handle_message(request: MessageRequest) -> MessageResponse:
    return llm_sub(request.text)