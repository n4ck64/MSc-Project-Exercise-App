from ollama import generate
from ollama import chat
import ollama
import psycopg2

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()


def retrieve_exercises(query, top_k=3):
    """Queries the database to retrieve the three most relevant exercises
    based on the user's input and the corresponding generated embedding"""
    response = ollama.embed(model="nomic-embed-text", input=query)
    embedding = response.embeddings[0]
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


system_prompt = """You are a medical expert that provides advise on exercises. You do not shy away from answering questions. 
Do not provide an introduction.
Reference relevant details from earlier in the conversation."""

review_prompt = """You are a strict medical peer-reviewer and board-certified physician. 
Audit the given AI-generated medical response for clinical accuracy, 
safety, and alignment with current medical guidelines in comparison to the user's question.
Provide a concise audit covering exactly these five points:
1. Factual Errors: Identify any false claims, outdated guidelines, or medical inaccuracies.
2. Dangerous Omissions: State any critical red-flag symptoms, safety warnings, or alternative diagnoses the AI missed.
3. Safety Rating: Classify the original advice as [Safe], [Needs Correction], or [Dangerous].
4. Biomechanical Analysis: Mentally simulate the physics of every exercise described. 
Verify that the resistance vector actually targets the intended muscle group 
through its proper anatomical range of motion. If the mechanics are physically impossible or target the wrong muscle, 
flag it as a Factual Error.
5. Corrected Version: Rewrite the response so it is clinically accurate, safe, and actionable. 

Be direct, objective, and uncompromising on patient safety. Do not write any conversational intro."""

final_prompt = """You are an expert text-rewriter and communicator engine.
Your job is to take the medical advice provided and rewrite it to sound conversational, direct 
and easy to understand. 
Rules:
1. Look at the Review Audit. If a 'Corrected Version' is provided, rewrite the 'Original Advice' using that. 
If the audit says there are no errors, rewrite the 'Original Advice'.
2. Your very first sentence must jump directly into addressing the query. 
3. Keep the safety warnings intact but phrased naturally.
4. Translate medical jargon into plain English. 
Forbidden phrases: 'revised version', 'updated advice', 'let me rewrite', 'here is a correction', 
'Hello', 'Sure thing', 'Great question', 'Of course', 'Absolutely', 
'Happy [anything]', 'I understand', 'Engaging conversation!', 'Here is a more conversational version' or similar, 
'Here's a rewritten version of the original advice:' """

messages = []
while True:
    user_input = input(">>")
    if user_input.lower() == "exit":
        break
    response_content = ""
    retrieved = retrieve_exercises(user_input)
    rag_context = f"Relevant exercises from database:\n\n{retrieved}"
    print(rag_context)
    initial_response = chat("medical-expert:latest",
                            messages=[{"role": "system", "content": system_prompt}] +
                            messages +
                            [{"role": "user", "content": f"{rag_context}\n\nUser question: {user_input}"}],
                            options={
                                "temperature": 0.7,
                                "num_predict": 2048,
                                "num_ctx": 8192
                            },
                            stream=False)

    initial_text = initial_response.message.content

    double_check = chat("medical-expert:latest",
                        messages=[
                            {"role": "system", "content": review_prompt},
                            {"role": "user", "content": (
                                f"Original Question: {user_input}\n\nAI Response: {initial_text}")}
                        ],
                        options={
                            "temperature": 0.1,
                            "num_predict": 2048,
                            "num_ctx": 8192
                        },
                        stream=False)

    audit_text = double_check.message.content

    final_response = chat("llama3",
                          messages=[
                              {"role": "system", "content": final_prompt},
                              {"role": "user", "content": (
                                  f"Original Advice:\n{initial_text}\n\n"
                                  f"Review Audit:\n{audit_text}")}
                          ],
                          options={
                              "temperature": 0.1,
                              "num_predict": 2048,
                              "num_ctx": 8192
                          },
                          stream=True)

    print(f"Initial response: {initial_text}")
    print()
    print(f"Double check: {audit_text}")
    print()

    print("\nMy response: ", end="")
    for chunk in final_response:
        if chunk.message:
            content = chunk.message.content
            print(content, end='', flush=True)
            response_content += content
    print()
    messages += [
        {"role": "user", "content": user_input},
        {"role": "assistant", "content": response_content}
    ]
