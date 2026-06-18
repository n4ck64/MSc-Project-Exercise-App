"""
Contains the memory of the app.
"""


class Memory:
    """Keeps track of global chat history and any video summaries"""
    chat_history = []
    video_summary = None

    @classmethod
    def clear(cls):
        """cleans all chat history for current session"""
        cls.chat_history = []

    @classmethod
    def reset_video(cls):
        """wipes memory of any video summary"""
        cls.video_summary = None

    @classmethod
    def show_history(cls):
        """shows full chat history, used for debugging"""
        return Memory.chat_history
