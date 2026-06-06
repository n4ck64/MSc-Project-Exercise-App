import psycopg2
import ollama

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()

# Fetch all exercises without embeddings
cur.execute(
    "SELECT exercise_id, exercise_name, description FROM exercises WHERE embedding IS NULL")
exercises = cur.fetchall()

for exercise_id, exercise_name, description in exercises:
    text = f"{exercise_name}. {description}"
    response = ollama.embed(model="nomic-embed-text", input=text)
    embedding = response.embeddings[0]

    cur.execute(
        "UPDATE exercises SET embedding = %s WHERE exercise_id = %s",
        (embedding, exercise_id)
    )
    print(f"Embedded: {exercise_name}")

conn.commit()
cur.close()
conn.close()
print("Done.")
