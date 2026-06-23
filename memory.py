"""
Contains the memory of the app.
"""
import logging


class Memory:
    """Keeps track of global chat history and any video summaries"""
    chat_history = []
    video_summary = None
    video_probable_exercises = []
    last_exercises = []

    @classmethod
    def clear(cls):
        """cleans all chat history for current session"""
        cls.chat_history = []

    @classmethod
    def reset_video(cls):
        """wipes memory of any video summary"""
        logging.debug(f"Video summary: {cls.video_summary}")
        cls.video_summary = None

    @classmethod
    def show_history(cls):
        """shows full chat history, used for debugging"""
        return Memory.chat_history
