from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()

class MessageRequest(BaseModel):
    text: str
    session_id: str
    
class MessageResponce(BaseModel):
    text: str
    intent: str   # о чем спрашивал пользователь, тематика 
    
    
def llm_sub(text: str) -> MessageResponce:
    return MessageResponce(
        text='Здравствуйте! Чем могу помочь?',
        intent='greeting'
    )
    
@app.post('/message', response_model=MessageResponce)
def handle_message(request: MessageRequest) -> MessageResponce:
    return llm_sub(request.text)