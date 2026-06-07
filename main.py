"""
This is the brain of the app,
connecting backend with frontend.
"""
from fastapi import FastAPI
from pydantic import BaseModel

app = FastAPI()


class Message(BaseModel):
    content: str


@app.post("/chat")
async def chat_endpoint(message: Message):
    # your pipeline logic here
    response = run_pipeline(message.content)
    return {"response": response}
