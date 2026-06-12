"""
This module is responsible for the image/vision
recognition aspect of the app.
It gives feedback on physiques, form analysis,
and advice based on local LLMs.
"""
from ollama import chat
import ollama
import psycopg2
from PIL import Image
import numpy as np
import mediapipe as mp
import cv2


def analyse_image(image_path):
    """Takes the images of exercise or people and gives feedback"""

    with open(image_path, "rb") as f:
        image_data = f.read()

    response = chat("moondream", messages=[
        {"role": "user",
         "content": """The image will be either someone exercising, or just someone. If it is someone exercising, describe the position
        of all visible joints and any form issues you notice. If it is simnply a person, tell them where they can improve upon, fitness wise""",
         "images": [image_path]}
    ])
    return response.message.content.strip()


# def run_vision(media):

def analyse_video(video):
    """Takes video input, extracts every 30th frame,
    feeds it into mediapipe for joint position analysis,
    returns the final coordinates as a string to be fed
    to the local LLMs."""
    cap = cv2.VideoCapture(video)
    frame_count = 0
    frames = []  # list of total frames to be analysed from video

    while cap.isOpened():
        ret, frame = cap.read()  # ret is True if frame was read successfully
        if not ret:
            break

        if frame_count % 30 == 0:
            frames.append(frame)

        frame_count += 1

    cap.release()  # discards video from memory once extraction is finished

    mp_pose = mp.solutions.pose
    pose = mp_pose.Pose()

    all_frames = []

    for frame in frames:
        # cv2 is BGR, mp only accepts RGB, so frames need to be converted
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        results = pose.process(frame)
        if results.pose_landmarks:
            # each landmark has x, y, z coordinates which will be saved
            landmarks = results.pose_landmarks.landmark
            # the position for each bodypart will be saved against each frame in the dict below
            frame_data = {
                "left_shoulder": landmarks[mp_pose.PoseLandmark.LEFT_SHOULDER],
                "right_shoulder": landmarks[mp_pose.PoseLandmark.RIGHT_SHOULDER],
                "left_elbow": landmarks[mp_pose.PoseLandmark.LEFT_ELBOW],
                "right_elbow": landmarks[mp_pose.PoseLandmark.RIGHT_ELBOW],
                "left_wrist": landmarks[mp_pose.PoseLandmark.LEFT_WRIST],
                "right_wrist": landmarks[mp_pose.PoseLandmark.RIGHT_WRIST],
                "left_hip": landmarks[mp_pose.PoseLandmark.LEFT_HIP],
                "right_hip": landmarks[mp_pose.PoseLandmark.RIGHT_HIP],
                "left_knee": landmarks[mp_pose.PoseLandmark.LEFT_KNEE],
                "right_knee": landmarks[mp_pose.PoseLandmark.RIGHT_KNEE],
                "left_ankle": landmarks[mp_pose.PoseLandmark.LEFT_ANKLE],
                "right_ankle": landmarks[mp_pose.PoseLandmark.RIGHT_ANKLE],
                "left_heel": landmarks[mp_pose.PoseLandmark.LEFT_HEEL],
                "right_heel": landmarks[mp_pose.PoseLandmark.RIGHT_HEEL],
                "left_foot_index": landmarks[mp_pose.PoseLandmark.LEFT_FOOT_INDEX],
                "right_foot_index": landmarks[mp_pose.PoseLandmark.RIGHT_FOOT_INDEX]
            }
            # saves a dictionary for each frame extracted with all of the above coordinates
            all_frames.append(frame_data)

    summary = ""
    for i, frame in enumerate(all_frames):
        summary += f"Frame {i}:\n"
        for joint, landmark in frame.items():
            summary += f" {joint}: x={landmark.x:.2f}, y={landmark.y:.2f}, visibility = {landmark.visibility:.2f}\n"
    return summary
