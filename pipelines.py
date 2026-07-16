"""
This module handles the LLM pipeline for the fitness app.
It includes intent classification, injury detection, RAG retrieval,
and a three-model reponse pipeline (medical answerer, medical reviewer,
conversational rewriter)
"""
from ollama import chat
from prompts import *
from retrieval import retrieve_exercises, retrieve_exercise_names, retrieve_exercise_description
from memory import Memory
from llm import structured_chat
from classification import classify_intent, classify_injured_muscle, condense_query, classify_target_muscle
import logging


def run_chat_pipeline(user_input):
    """The main driver behind the chatting part of the app.
    Takes user input, clarifies intent, retrieves
    relevant exercises, reviews initial answer,
    and returns final response."""

    if user_input.strip().lower() == "/clear":
        # wipe the history for debugging
        Memory.clear()
        yield "Chat history cleared."
        return

    logging.debug("=" * 100)
    logging.debug(f"User's message: {user_input}")

    response_content = ""

    # resolve follow-ups into a standalone query up front, so both intent
    # classification and RAG retrieval operate on the resolved query
    rewritten_query = condense_query(user_input)
    logging.debug(f"User input rewritten as: {rewritten_query}")

    # determines user intent before proceeding
    intent = classify_intent(rewritten_query)
    logging.debug(f"Intent classified as: {intent}")

    if intent in ("EXERCISE_INJURY"):
        injured_muscle_ids = classify_injured_muscle(rewritten_query)
        logging.debug(f"Injured muscle: {injured_muscle_ids}")

        retrieved = retrieve_exercises(
            rewritten_query, injured_muscle_id=injured_muscle_ids)

    elif intent in ("EXERCISE_GENERAL"):
        target_muscle_ids = classify_target_muscle(rewritten_query)
        logging.debug(f"Target Muscle: {target_muscle_ids}")
        retrieved = retrieve_exercises(
            rewritten_query, target_muscle_id=target_muscle_ids)
        Memory.last_exercises = [
            line.replace("Exercise: ", "")
            for line in retrieved.split("\n")
            if line.startswith("Exercise: ")
        ]

    elif intent == "PLAN_GENERAL":
        Memory.plan_draft = "Ongoing"
        run_plan_pipeline(rewritten_query)

    elif intent == "PLAN_INJURY":
        injured_muscle_ids = classify_injured_muscle(rewritten_query)
        run_plan_pipeline(rewritten_query, injured_muscle_ids)

    elif intent in ("NUTRITION", "NUTRITION_PLAN"):
        retrieved = None  # nutrition talk requires no RAG
        for token in run_nutrition_pipeline(user_input):
            response_content += token
            yield token

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]

        logging.debug(f"Final response: {response_content}")

        return

    else:
        retrieved = None
        response = chat("llama3.1", messages=[
            {"role": "system",
                "content": "You are a helpful fitness assistant. Be conversational and brief."}] + Memory.chat_history[-10:]
            + [{"role": "user", "content": user_input}
               ], stream=True)

        for chunk in response:
            token = chunk.message.content
            response_content += token
            yield token

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]

        return

    logging.info(f"RAG retrieved: {retrieved}")
    # below is the result of the SQL queries
    rag_context = f"Relevant exercises:\n\n{retrieved}"

    # a medical LLM responds given the user query and the SQL output
    yield "Thinking..."
    initial_response = chat("llama3.1",
                            # the system prompt
                            messages=[{"role": "system", "content": SYSTEM_PROMPT}] +
                            # context from the last 5 messages
                            Memory.chat_history[-10:]
                            # the user query plus the SQL results
                            + [{"role": "user", "content": f"{rag_context}\n\nUser question: {user_input}"}],
                            options={
                                # how creative the model can get -> 0.0 is static, 1.0 is unpredictable
                                "temperature": 0.7,
                                # maximum number of tokens the model can generate in one response
                                "num_predict": 8192,
                                # context window size, exceeding this causes the model to forget prior info
                                "num_ctx": 8192
                            },
                            stream=False)

    initial_text = initial_response.message.content
    logging.debug(f"LLM initial response: {initial_text}")

    for token in review_and_rewrite(user_input, initial_text, EXERCISE_REVIEW_PROMPT, retrieved):
        response_content += token
        yield token

    logging.debug(f"Final response: {response_content}")
    Memory.chat_history += [
        {"role": "user", "content": user_input},
        # adds the user query and subsequent LLM response to the chat history
        {"role": "assistant", "content": response_content}
    ]


def run_video_pipeline(user_input, video_summary=None, video_choice=None):
    """runs only when video is present, it is responsible for
    the back and forth interactions - extracts joint coordinates from video, generates
    a natural language interpretation of them, clarifies with the user what
    exercise is shown, and then runs pipeline based on that."""

    logging.debug("=" * 100)
    logging.debug(f"User's message: {user_input}")

    if video_summary:
        yield "Processing..."

        first_step = chat("medical-expert:latest", messages=[{"role": "system", "content":
                                                              """You are an exercise analyst. 
        Based on the given joint position coordinates and user context
        identify the exercise being performed and describe it in natural language, focusing on:
        - Which muscle groups are being used
        - The movement pattern
        - The body position
        Keep it concise, 2-3 sentences max."""}, {"role": "user", "content":
                                                  f"Coordinates: {video_summary}\nUser context: {user_input}"}],
                          options={
            "temperature": 0.0,
            "num_predict": 8192,
            "num_ctx": 8192
        },
            stream=False)
        Memory.video_summary = first_step.message.content  # saves it for future use
        logging.debug(f"Video summary: {Memory.video_summary}")

        probable_exercises = retrieve_exercise_names(
            first_step.message.content)
        Memory.video_probable_exercises = probable_exercises
        yield f"CHOICES:To confirm, which exercise is shown in the video?|{probable_exercises[0]},{probable_exercises[1]},{probable_exercises[2]}"

    if video_choice:
        if video_choice == "manual":
            yield "Please type the name of the exercise shown in the video."
            return

        exercise_description = retrieve_exercise_description(user_input)

        if not exercise_description:
            probable_exercises = Memory.video_probable_exercises
            yield f"CHOICES:That was not recognised, please choose from the list again:|{probable_exercises[0]},{probable_exercises[1]},{probable_exercises[2]}"
            return

        response_content = ""
        yield "Thinking..."
        response = chat("medical-expert:latest", messages=[
            {"role": "system", "content":
             "You are a fitness coach analysing my exercise form. Be specific and direct."},
            {"role": "user", "content": f"""I am performing: {user_input}\n
            Correct form reference: {exercise_description}\n
            What was observed: {Memory.video_summary}\n
            Rate my form and give specific corrections."""}
        ], stream=True)
        for chunk in response:
            token = chunk.message.content
            response_content += token
            yield token

        Memory.reset_video()

        logging.debug(f"Video response: {response_content}")

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]


def run_nutrition_pipeline(user_input):
    """when the intent is classified as NUTRITION or NUTRITION_PLAN,
    the LLM does not do RAG and instead shifts to a nutritionist role"""
    yield "Hungry..."

    logging.debug(f"User's message: {user_input}")

    initial_response = chat("medical-expert:latest",
                            # the system prompt
                            messages=[{"role": "system", "content": NUTRITION_PROMPT}] +
                            # context from the last 5 messages
                            Memory.chat_history[-10:]
                            # the user query plus the SQL results
                            + [{"role": "user", "content": f"User question: {user_input}"}],
                            options={
                                "temperature": 0.7,
                                "num_predict": 8192,
                                "num_ctx": 8192
                            },
                            stream=False)

    initial_text = initial_response.message.content
    logging.debug(f"Nutrition first response: {initial_text}")

    yield from review_and_rewrite(user_input, initial_text, NUTRITION_REVIEW_PROMPT)


def review_and_rewrite(user_input, response, review_prompt, rag_context=None):
    """takes the LLM's initial response, reviews it under a list of criteria,
    and rewrites it to be conversational and layman-friendly"""

    yield "Reviewing..."

    if rag_context:
        review_input = (f"Approved exercises:\n{rag_context}\n\n"
                        f"Original Question: {user_input}\n\nAI Response: {response}")
    else:
        review_input = f"Original Question: {user_input}\n\nAI Response: {response}"

    audit = structured_chat("qwen2.5:7b", review_prompt,
                            review_input, REVIEW_SCHEMA)
    corrected = response if audit["verdict"] == "Safe" else audit["corrected_response"]

    logging.debug(f"Reviewer response: {audit}")

    final_response = chat("llama3.1",
                          messages=[
                              {"role": "system", "content": FINAL_PROMPT},
                              {"role": "user", "content": (
                                  f"Verified Advice:\n{corrected}")}
                          ],
                          options={
                              "temperature": 0.1,
                              "num_predict": 4096,
                              "num_ctx": 8192
                          },
                          stream=True)  # final response will stream as it is being generated

    for chunk in final_response:
        token = chunk.message.content
        yield token


def run_plan_pipeline(user_input, injuries=None):
    """runs the plan making loop and generation"""
    slots = structured_chat("llama3.1", INTAKE_PROMPT,
                            user_input, INTAKE_SCHEMA)
    pass
