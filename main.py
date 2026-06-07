"""
This is the brain of the app,
connecting backend with frontend.
"""
from fastapi import FastAPI
from pydantic import BaseModel
from pipeline import run_pipeline
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    content: str


@app.post("/chat")
async def chat_endpoint(message: Message):
    # your pipeline logic here
    response = run_pipeline(message.content)
    return {"response": response}
