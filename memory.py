"""
Contains the memory of the app.
"""
import logging


class Memory:
    """Keeps track of global chat history, video summaries, probable video exercises
    and steps in the plan-making process"""
    chat_history = []
    video_summary = None  # the frame coordinates along with visibility for each joint
    # the choices presented to the user after video is analysed
    video_probable_exercises = []
    plan_slots = None      # accumulating intake slots; None = no plan in progress
    finished_plan = None   # the built plan JSON the Plans page fetches
    # plan-edit awaiting a clarifying answer: {context, question, turns}; None = none pending
    pending_edit = None
    # food-log awaiting a yes/no before it is written: {food_id, food_name, grams,
    # question}; None = none pending. Nothing is written until the user confirms.
    pending_food_log = None
    # which user the above conversational state belongs to (dev switcher)
    current_user_id = None

    @classmethod
    def clear(cls):
        """cleans all chat history for current session"""
        cls.chat_history = []
        cls.plan_slots = None
        cls.finished_plan = None
        cls.pending_edit = None
        cls.pending_food_log = None

    @classmethod
    def reset_video(cls):
        """wipes memory of any video summary"""
        logging.debug(f"Video summary: {cls.video_summary}")
        cls.video_summary = None

    @classmethod
    def show_history(cls):
        """shows full chat history, used for debugging"""
        return Memory.chat_history
