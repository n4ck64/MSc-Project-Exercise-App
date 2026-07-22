"""
The functions here classify information from text using llama3.1
"""

from memory import Memory
from prompts import INTENT_PROMPT, TARGET_MUSCLE_PROMPT, INJURED_MUSCLE_PROMPT, CONDENSE_PROMPT, MUSCLE_SCHEMA, QUERY_SCHEMA, INTENT_SCHEMA
from llm import structured_chat


def classify_intent(user_input):
    """Takes the user's query and classifies it into one of seven
    intent labels, using recent history for context."""
    history = "\n".join(
        f'{m["role"]}: {m["content"]}' for m in Memory.chat_history[-4:])
    return structured_chat(
        "llama3.1", INTENT_PROMPT,
        f"Previous conversation:\n{history}\n\nMessage to classify: {user_input}",
        INTENT_SCHEMA)["intent"]


def classify_injured_muscle(user_input):
    """Takes user input and if an injury is mentioned, returns the list of injured
    muscle_ids (empty list if none) — same shape as classify_target_muscle, so it
    can be passed straight to retrieve_exercises' ANY(%s) filter."""
    return structured_chat("llama3.1", INJURED_MUSCLE_PROMPT, user_input, MUSCLE_SCHEMA)["muscle_ids"]


def classify_target_muscle(query):
    """Returns the muscle_id the user wants to train, 0 if no muscle is mentioned"""
    return structured_chat("llama3.1", TARGET_MUSCLE_PROMPT, query, MUSCLE_SCHEMA)["muscle_ids"]


def condense_query(user_input):
    """Rewrites a follow-up into a standalone query using recent history, so the
    RAG embeds the user's actual intent instead of the previous reply. Returns
    self-contained queries unchanged, and skips the LLM call on the first turn."""
    if not Memory.chat_history:
        return user_input

    history = "\n".join(
        f'{m["role"]}: {m["content"]}' for m in Memory.chat_history[-4:])
    result = structured_chat(
        "llama3.1", CONDENSE_PROMPT,
        f"Conversation:\n{history}\n\nLatest message: {user_input}",
        QUERY_SCHEMA)

    return result["query"].strip() or user_input
