"""
All database retrieval functions live here
"""

import ollama
import psycopg2
from memory import Memory

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()


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
                WHERE exercise_name ILIKE %s
                """, (name,))

    result = cur.fetchone()
    if result is None:
        return None
    return result[0]
