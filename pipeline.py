"""
This module handles the LLM pipeline for the fitness app.
It includes intent classification, injury detection, RAG retrieval,
and a three-model reponse pipeline (medical answerer, medical reviewer,
conversational rewriter)
"""
from ollama import chat
import ollama
import psycopg2
from prompts import *

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()


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


def classify_intent(user_input):
    """Takes the user's initial query and classifies it in one of five categories:
    general exercise query, exercise query with an injury, making a general plan,
    making a general plan with an injury, or just chitchatting."""

    response = chat("llama3", messages=[
        {"role": "system", "content": f"""You are a classifier. 
        Output exactly one of these labels and nothing else:
        EXERCISE_GENERAL
        EXERCISE_INJURY
        PLAN_GENERAL
        PLAN_INJURY
        CHITCHAT

        No explanation. No punctuation. No other text. Just the label.
        Previous conversation:
        {Memory.chat_history[-4:]} 

        Examples:
        "what exercises can I do?" -> EXERCISE_GENERAL
        "I hurt my knee, what can I do?" -> EXERCISE_INJURY
        "make me a workout plan" -> PLAN_GENERAL
        "make me a plan, I have a bad back" -> PLAN_INJURY
        "hi how are you" -> CHITCHAT"""},
        {"role": "user", "content": user_input}
    ])
    return response.message.content.strip()


def extract_injured_muscle(user_input):
    """Takes user input and if an injury is mentioned, 
    specifies which muscle is the injured one"""

    response = chat("llama3", messages=[
        {"role": "system", "content": EXTRACTION_PROMPT},
        {"role": "user", "content": user_input}
    ])
    # result should be part of the list, if not return None
    result = response.message.content.strip()
    return int(result) if result.isdigit() else None


def retrieve_exercises(query, top_k=3, injured_muscle_id=None):
    """Queries the database to retrieve the three most relevant exercises
    based on the user's input and the corresponding generated embedding"""
    rag_query = query if len(
        Memory.chat_history) == 0 else Memory.chat_history[-1]["content"] + " " + query
    # if first message, the RAG uses the query to do its retrieval, else uses the query plus the previous message
    response = ollama.embed(model="nomic-embed-text", input=rag_query)
    embedding = response.embeddings[0]
    if injured_muscle_id:
        cur.execute("""
                    SELECT exercise_name, description, type, difficulty, equipment
                    FROM exercises
                    WHERE exercise_id NOT IN (
                        SELECT exercise_id FROM muscles_exercised WHERE muscle_id = %s
                        )
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (injured_muscle_id, embedding, top_k))
    else:
        cur.execute("""
                    SELECT exercise_name, description, type, difficulty, equipment
                    FROM exercises
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))

    rows = cur.fetchall()
    results = []
    for name, description, type_, difficulty, equipment in rows:
        results.append(
            f"Exercise: {name}\nType: {type_} | Difficulty: {difficulty} | Equipment: {equipment}\nDescription: {description}")
    return "\n\n".join(results)


def retrieve_exercise_names(description, top_k=3):
    """Queries the database to retrieve the three most relevant exercises
    based on the provided description and the corresponding generated embedding.
    This function is only used for the video analysis."""
    response = ollama.embed(model="nomic-embed-text", input=description)
    embedding = response.embeddings[0]
    cur.execute("""
                SELECT exercise_name
                FROM exercises
                ORDER BY embedding <=> %s::vector
                LIMIT %s
                """, (embedding, top_k))

    rows = cur.fetchall()
    results = []
    for name in rows:
        results.append(name[0])
    return results


def retrieve_exercise_description(name):
    """Retrieves the description of the exercise that matches the given name.
    Used in the last step of the video analysis pipeline."""
    cur.execute("""
                SELECT description
                FROM exercises
                WHERE exercise_name = %s
                """, (name,))
    return cur.fetchone()[0]


def run_pipeline(user_input):
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
        injured_muscle_id = extract_injured_muscle(user_input)
        retrieved = retrieve_exercises(
            user_input, injured_muscle_id=injured_muscle_id)

    elif intent in ("EXERCISE_GENERAL", "PLAN_GENERAL"):
        retrieved = retrieve_exercises(user_input)

    else:
        retrieved = None  # skip RAG for regular chats
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
                                "temperature": 0.7,  # how creative the model can get -> 0.0 is static, 1.0 is unpredictable
                                "num_predict": 8192,  # maximum number of tokens the model can generate in one response
                                "num_ctx": 8192  # context window size, exceeding this causes the model to forget prior info
                            },
                            stream=False)

    initial_text = initial_response.message.content

    # the same LLM with a different system prompt reviews the above response under a list of criteria
    yield "Reviewing..."
    double_check = chat("medical-expert:latest",
                        messages=[
                            {"role": "system", "content": REVIEW_PROMPT},
                            {"role": "user", "content": (
                                f"Original Question: {user_input}\n\nAI Response: {initial_text}")}
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
                                  f"Original Advice:\n{initial_text}\n\n"
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
        first_step = chat("medical-expert:latest", messages=[{"role": "system", "content": """You are an exercise analyst. 
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
