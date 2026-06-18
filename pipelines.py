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
from classification import classify_intent, classify_injured_muscle


def run_main_pipeline(user_input):
    """The main driver behind the chatbot.
    Takes user input, clarifies intent, retrieves
    relevant exercises, reviews initial answer,
    and returns final response."""

    if user_input.strip().lower() == "/clear":
        # wipe the history for debugging
        Memory.clear()
        yield "Chat history cleared."
        return

    response_content = ""
    # determines user intent before proceeding
    intent = classify_intent(user_input)

    if intent in ("EXERCISE_INJURY", "PLAN_INJURY"):
        injured_muscle_id = classify_injured_muscle(user_input)
        retrieved = retrieve_exercises(
            user_input, injured_muscle_id=injured_muscle_id)

    elif intent in ("EXERCISE_GENERAL", "PLAN_GENERAL"):
        retrieved = retrieve_exercises(user_input)

    elif intent in ("NUTRITION", "NUTRITION_PLAN"):
        retrieved = None  # nutrition talk requires no RAG
        for token in run_nutrition_pipeline(user_input):
            response_content += token
            yield

        Memory.chat_history += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]

        return

    else:
        retrieved = None
        response = chat("llama3", messages=[
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

    # below is the result of the SQL queries
    rag_context = f"Relevant exercises:\n\n{retrieved}"

    # a medical LLM responds given the user query and the SQL output
    yield "Thinking..."
    initial_response = chat("medical-expert:latest",
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

    for token in review_and_rewrite(user_input, initial_text):
        response_content += token
        yield token

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
    yield "Processing..."
    if video_summary:
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

        probable_exercises = retrieve_exercise_names(
            first_step.message.content)
        yield f"CHOICES:{probable_exercises[0]},{probable_exercises[1]},{probable_exercises[2]}"
    if video_choice:
        exercise_description = retrieve_exercise_description(user_input)
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
            yield chunk.message.content
        Memory.reset_video()


def run_nutrition_pipeline(user_input):
    """when the intent is classified as NUTRITION or NUTRITION_PLAN,
    the LLM does not do RAG and instead shifts to a nutritionist role"""
    yield "Hungry..."

    initial_response = chat("medical-expert:latest",
                            # the system prompt
                            messages=[{"role": "system", "content": NUTRITION_PROMPT}] +
                            # context from the last 5 messages
                            Memory.chat_history[-10:]
                            # the user query plus the SQL results
                            + [{"role": "user", "content": f"{rag_context}\n\nUser question: {user_input}"}],
                            options={
                                "temperature": 0.7,  # how creative the model can get -> 0.0 is static, 1.0 is unpredictable
                                "num_predict": 8192,  # maximum number of tokens the model can generate in one response
                                "num_ctx": 8192  # context window size, exceeding this causes the model to forget prior info
                            },
                            stream=False)

    initial_text = initial_response.message.content


def review_and_rewrite(user_input, response):
    """takes the LLM's initial response, reviews it under a list of criteria,
    and rewrites it to be conversational and layman-friendly"""

    yield "Reviewing..."
    double_check = chat("medical-expert:latest",
                        messages=[
                            {"role": "system", "content": REVIEW_PROMPT},
                            {"role": "user", "content": (
                                f"Original Question: {user_input}\n\nAI Response: {response}")}
                        ],
                        options={
                            "temperature": 0.1,
                            "num_predict": 4096,
                            "num_ctx": 8192
                        },
                        stream=False)

    audit_text = double_check.message.content

    final_response = chat("llama3",
                          messages=[
                              {"role": "system", "content": FINAL_PROMPT},
                              {"role": "user", "content": (
                                  f"Original Advice:\n{response}\n\n"
                                  f"Review Audit:\n{audit_text}")}
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
