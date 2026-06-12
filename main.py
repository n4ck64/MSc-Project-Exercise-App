"""
This is the brain of the app,
connecting backend with frontend.
"""
from fastapi import FastAPI, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pipeline import run_pipeline
from fastapi.middleware.cors import CORSMiddleware
from vision import analyse_image, analyse_video
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5500"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class Message(BaseModel):
    content: str
    image_path: str | None = None


@app.post("/chat")
async def chat_endpoint(message: Message):
    """the pipeline logic runs here"""
    if message.image_path:
        return StreamingResponse(analyse_image(message.image_path, message.content), media_type="text/plain")
    return StreamingResponse(run_pipeline(message.content), media_type="text/plain")


@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    temp_path = f"/tmp/temp_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contents)

    return {"file_path": temp_path}
