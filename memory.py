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
    last_exercises = []    # exercise names the current turn's answer is grounded on
    # the raw retrieved context the current turn's answer was grounded on, kept so the
    # evaluation harness can log it at generation time (RAGAS faithfulness needs it and
    # it cannot be reconstructed after the fact). Unused by the app itself.
    last_rag_context = None
    # the intent the current turn was classified as, kept so the evaluation harness
    # can detect misrouting (a question sent to the plan pipeline yields a clarifying
    # question, not an answer, and must not be scored as if it were one)
    last_intent = None
    plan_slots = None      # accumulating intake slots; None = no plan in progress
    finished_plan = None   # the built plan JSON the Plans page fetches
    # plan-edit awaiting a clarifying answer: {context, question, turns}; None = none pending
    pending_edit = None
    # food-log awaiting a yes/no before it is written: {food_id, food_name, grams,
    # question}; None = none pending. Nothing is written until the user confirms.
    pending_food_log = None
    # which user the above conversational state belongs to (dev only)
    current_user_id = None

    @classmethod
    def clear(cls):
        """cleans all chat history for current session"""
        cls.chat_history = []
        cls.last_exercises = []
        cls.last_rag_context = None
        cls.last_intent = None
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
