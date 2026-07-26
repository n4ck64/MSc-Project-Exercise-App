"""
Generates embeddings for every food in the 'foods' table using the same
Ollama model as the exercises (nomic-embed-text, 768 dims).

Mirrors generate_embeddings.py, but iterates by the surrogate 'id' (food_code
is not unique in CoFID) and commits in batches so the ~2,900 embeds are
resumable: the WHERE embedding IS NULL guard means a re-run only fills gaps.
"""

import getpass
import os

import ollama
import psycopg2

conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()

cur.execute(
    "SELECT id, food_name, description FROM foods WHERE embedding IS NULL")
foods = cur.fetchall()
print(f"{len(foods)} foods to embed.")

for i, (food_id, food_name, description) in enumerate(foods, start=1):
    # nomic-embed-text is asymmetric: documents need the search_document: prefix
    # (queries use search_query:), otherwise retrieval quality drops noticeably.
    text = f"search_document: {food_name}. {description}"
    response = ollama.embed(model="nomic-embed-text", input=text)
    embedding = response.embeddings[0]

    cur.execute(
        "UPDATE foods SET embedding = %s WHERE id = %s",
        (embedding, food_id)
    )

    if i % 100 == 0:
        conn.commit()
        print(f"  embedded {i}/{len(foods)}")

conn.commit()
cur.close()
conn.close()
print("Done.")
