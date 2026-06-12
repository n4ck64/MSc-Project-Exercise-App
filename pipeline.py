"""
This module handles the LLM pipeline for the fitness app.
It includes intent classification, injury detection, RAG retrieval,
and a three-model reponse pipeline (medical answerer, medical reviewer,
conversational rewriter)
"""
from ollama import chat
import ollama
import psycopg2

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()


def classify_intent(user_input, messages):
    """Takes the user's initial query and classifies it in one of five categories:
    general exercise query, exercise query with an injury, making a general plan,
    making a general plan with an injury, or just chitchatting."""

    context = "\n".join([m["content"]
                        for m in messages[-4:]])  # last 2 exchanges
    response = chat("llama3", messages=[
        {"role": "system", "content": f"""You are a classifier. Output exactly one of these labels and nothing else:
    EXERCISE_GENERAL
    EXERCISE_INJURY
    PLAN_GENERAL
    PLAN_INJURY
    CHITCHAT

    No explanation. No punctuation. No other text. Just the label.
    Previous conversation:
    {context}

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
        {"role": "system", "content": """You are a muscle ID extractor. Your only job is to return a single number.
    Rules:
    - Read the user message
    - Find the injured muscle
    - Return ONLY the matching number from this list, nothing else whatsoever
    - Do not explain, do not advise, do not add any text
    - If unsure, return 0

    101=Biceps, 102=Triceps, 103=Forearm flexors, 104=Forearm extensors,
    201=Anterior deltoid, 202=Lateral deltoid, 203=Posterior deltoid, 204=Rotator cuff,
    301=Pectoralis major, 302=Pectoralis minor,
    401=Upper trapezius, 402=Middle trapezius, 403=Lower trapezius, 404=Latissimus dorsi, 405=Rhomboids, 406=Levator scapulae, 407=Erector spinae,
    501=Rectus abdominis, 502=Obliques, 503=Transversus abdominis,
    601=Gluteus maximus, 602=Gluteus medius, 603=Gluteus minimus,
    701=Quadriceps, 702=Hamstrings, 703=Abductors,
    801=Calves, 802=Shins, 803=Peroneals"""},
        {"role": "user", "content": user_input}
    ])
    # result should be part of the list, if not return None
    result = response.message.content.strip()
    return int(result) if result.isdigit() else None


def retrieve_exercises(query, top_k=3, injured_muscle_id=None):
    """Queries the database to retrieve the three most relevant exercises
    based on the user's input and the corresponding generated embedding"""
    rag_query = query if len(
        messages) == 0 else messages[-1]["content"] + " " + query
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


SYSTEM_PROMPT = """ IMPORTANT: Never use bullet points, numbered lists, or any list formatting. 
Write only in flowing prose paragraphs.

You are a medical expert that provides advise on exercises.
You do not shy away from answering questions. 
Do not provide an introduction.
Reference relevant details from earlier in the conversation."""

REVIEW_PROMPT = """IMPORTANT: Never use bullet points, numbered lists, or any list formatting. 
Write only in flowing prose paragraphs.
You are a strict medical peer-reviewer and board-certified physician. 
Audit the given AI-generated medical response for clinical accuracy, 
safety, and alignment with current medical guidelines in comparison to the user's question.
Only flag omissions that are directly relevant to the user's specific injury or condition. 
Do not introduce unrelated medical conditions.
The original question is always accurate and should be treated as ground truth. 
Do not question or contradict what the user has stated about themselves.
Provide a concise audit covering exactly these five points:
1. Factual Errors: Identify any false claims, outdated guidelines, or medical inaccuracies.
2. Dangerous Omissions: State any critical red-flag symptoms, safety warnings, or alternative diagnoses the AI missed.
3. Safety Rating: Classify the original advice as [Safe], [Needs Correction], or [Dangerous].
4. Biomechanical Analysis: Mentally simulate the physics of every exercise described. 
Verify that the resistance vector actually targets the intended muscle group 
through its proper anatomical range of motion. If the mechanics are physically impossible or target the wrong muscle, 
flag it as a Factual Error.
5. Corrected Version: Rewrite the response so it is clinically accurate, safe, and actionable. """

FINAL_PROMPT = """IMPORTANT: Never use bullet points, numbered lists, or any list formatting. 
Write only in flowing prose paragraphs.You are an expert text-rewriter and communicator engine.
Your job is to take the medical advice provided and rewrite it to sound conversational, direct 
and easy to understand. 
Rules:
1. Look at the Review Audit. If a 'Corrected Version' is provided, rewrite the 'Original Advice' using that. 
If the audit says there are no errors, rewrite the 'Original Advice'.
2. Your very first sentence must jump directly into addressing the query. 
3. Keep the safety warnings intact but phrased naturally.
4. Translate medical jargon into plain English. 
Forbidden phrases: 'revised version', 'updated advice', 'let me rewrite', 'here is a correction', 
'Hello', 'Sure thing', 'Great question', 'Of course', 'Absolutely', "Let's get started!",
'Happy [anything]', 'I understand', 'Engaging conversation!', 'Here is a more conversational version' or similar, 
'Here's a rewritten version of the original advice:', 'Note:', "I've rewritten", 'according to the rules', 
'(Note: The original advice has been rewritten to meet the rules.)', 'Let's get down to business!'"""

messages = []  # chat history


def run_pipeline(user_input):
    """The main driver behind the chatbot.
    Takes user input, clarifies intent, retrieves
    relevant exercises, reviews initial answer,
    and returns final response"""
    global messages
    response_content = ""
    # determines user intent before proceeding
    intent = classify_intent(user_input, messages[:-10])
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
                "content": "You are a helpful fitness assistant. Be conversational and brief."}] + messages[-10:]
            + [{"role": "user", "content": user_input}
               ], stream=False)
        answer = response.message.content
        response_content += response.message.content
        messages += [
            {"role": "user", "content": user_input},
            {"role": "assistant", "content": response_content}
        ]
        return answer
    # below is the result of the SQL queries
    rag_context = f"Relevant exercises:\n\n{retrieved}"

    initial_response = chat("medical-expert:latest",
                            # the system prompt
                            messages=[{"role": "system", "content": SYSTEM_PROMPT}] +
                            messages[-10:]  # context from the last 5 messages
                            # the user query plus the SQL results
                            + [{"role": "user", "content": f"{rag_context}\n\nUser question: {user_input}"}],
                            options={
                                "temperature": 0.7,  # how creative the model can get -> 0.0 is static, 1.0 is unpredictable
                                "num_predict": 8192,  # maximum number of tokens the model can generate in one response
                                "num_ctx": 8192  # context window size, exceeding this causes the model to forget prior info
                            },
                            stream=False)

    initial_text = initial_response.message.content

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
                          stream=False)  # final response will stream as it is being generated

    print(f"Intent: {intent}")
    print()
    print(f"Initial response: {initial_text}")
    print()
    print(f"Double check: {audit_text}")
    print()
    response_content += final_response.message.content
    answer = final_response.message.content

    messages += [
        {"role": "user", "content": user_input},
        # adds the user query and subsequent LLM response to the chat history
        {"role": "assistant", "content": response_content}
    ]
    return answer
