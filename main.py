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


@app.post("/chat")
async def chat_endpoint(message: Message):
    # the pipeline logic runs here
    return StreamingResponse(run_pipeline(message.content), media_type="text/plain")


@app.post("/upload")
async def upload_endpoint(file: UploadFile = File(...)):
    contents = await file.read()
    temp_path = f"/tmp/temp_{file.filename}"
    with open(temp_path, "wb") as f:
        f.write(contents)

    if file.content_type.startswith("image"):
        response = analyse_image(temp_path)
    elif file.content_type.startswith("video"):
        response = analyse_video(temp_path)
    else:
        return {"response": "Please upload an image or video file"}

    os.remove(temp_path)

    return {"response": response}
