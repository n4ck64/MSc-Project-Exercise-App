"""
The functions here classify information from text using llama3.1
"""

from ollama import chat
from memory import Memory
from prompts import EXTRACTION_PROMPT, CONDENSE_PROMPT
import re


def classify_intent(user_input):
    """Takes the user's initial query and classifies it in one of seven categories:
    general exercise query, exercise query with an injury, making a general plan,
    making a general plan with an injury, or just chitchatting."""

    INTENT_LABELS = ["EXERCISE_GENERAL", "EXERCISE_INJURY",
                     "PLAN_GENERAL", "PLAN_INJURY", "NUTRITION_PLAN", "NUTRITION", "CHITCHAT"]

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


def _clean_query(text):
    """Strips any preamble/quotes a chatty model may add around the rewritten
    query, leaving a bare string that is safe to embed. Returns "" if nothing
    usable is left (the caller falls back to the original query)."""
    # if the model prefaced with an explanation, keep the last non-empty line
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    text = lines[-1] if lines else ""
    text = text.strip("'\"").strip()
    # drop a leading "<label>:" the model might prepend
    lowered = text.lower()
    for prefix in ("standalone query:", "search query:", "rewritten query:", "query:"):
        if lowered.startswith(prefix):
            text = text[len(prefix):].strip("'\" ").strip()
            break
    return text


def condense_query(user_input):
    """Rewrites a follow-up into a standalone query using recent history, so the
    RAG embeds the user's actual intent instead of the previous reply. Returns
    self-contained queries unchanged, and skips the LLM call on the first turn."""
    if not Memory.chat_history:
        return user_input

    history = "\n".join(
        f'{m["role"]}: {m["content"]}' for m in Memory.chat_history[-4:])
    response = chat("llama3.1", messages=[
        {"role": "system", "content": CONDENSE_PROMPT},
        {"role": "user",
         "content": f"Conversation:\n{history}\n\nLatest message: {user_input}"}
    ])
    return _clean_query(response.message.content) or user_input
