from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)


def test_message_returns_200():
    responce = client.post('/message', json={
        'text': 'привет',
        'session_id': '123'
    })
    assert responce.status_code == 200
    
    
def test_message_returns_correct_fields():
    responce = client.post('/message', json={
        'text': 'привет',
        'session_id': '123'
    })
    data = responce.json()
    assert 'text' in data
    assert 'intent' in data
    
    
def test_message_without_text_returns_422():
    responce = client.post('/message', json={
        'session_id': '123'
    })
    assert responce.status_code == 422