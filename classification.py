"""
The functions here classify information from text using llama3
"""

from ollama import chat
from memory import Memory
from prompts import EXTRACTION_PROMPT
import re


def classify_intent(user_input):
    """Takes the user's initial query and classifies it in one of seven categories:
    general exercise query, exercise query with an injury, making a general plan,
    making a general plan with an injury, or just chitchatting."""

    INTENT_LABELS = ["EXERCISE_GENERAL", "EXERCISE_INJURY",
                     "PLAN_GENERAL", "PLAN_INJURY", "NUTRITION", "NUTRITION_PLAN", "CHITCHAT"]

    response = chat("llama3.1", messages=[
        {"role": "system", "content": f"""You are a classifier.
        Output exactly one of these labels and nothing else:
        EXERCISE_GENERAL
        EXERCISE_INJURY
        PLAN_GENERAL
        PLAN_INJURY
        NUTRITION
        NUTRITION_PLAN
        CHITCHAT

        No explanation. No punctuation. No other text. Just the label.
        Previous conversation:
        {Memory.chat_history[-4:]} 

        Examples:
        "what exercises can I do?" -> EXERCISE_GENERAL
        "I hurt my knee, what can I do?" -> EXERCISE_INJURY
        "make me a workout plan" -> PLAN_GENERAL
        "make me a plan, I have a bad back" -> PLAN_INJURY
        "hi how are you" -> CHITCHAT
        "what foods are rich in protein? -> NUTRITION
        "I want to bulk in a healthy way, what do you recommend? -> NUTRITION_PLAN"""},
        {"role": "user", "content": user_input}
    ])

    raw = response.message.content.upper()

    for label in INTENT_LABELS:
        if label in raw:
            return label
    return "CHITCHAT"


def classify_injured_muscle(user_input):
    """Takes user input and if an injury is mentioned, 
    specifies which muscle is the injured one"""

    response = chat("llama3.1", messages=[
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": user_input}
    ])
    # result should be part of the list, if not return None

    match = re.search(r"\d+", response.message.content)

    return int(match.group()) if match else None
