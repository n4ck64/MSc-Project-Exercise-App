import csv
import psycopg2

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()

# Muscles should be imported first, as they are referenced in other tables, such as muscles_exercised
with open('data/Muscles-Muscles.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cur.execute(
            "INSERT INTO muscles (muscle_id, muscle_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (int(row['muscle_id']), row['muscle_name'].strip())
        )
print("Muscles imported.")

# Import exercises
with open('data/Exercises-Exercises.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        if not row['exercise_name'].strip():  # skip blank rows
            continue
        cur.execute(
            "INSERT INTO exercises (exercise_id, exercise_name, description, type, difficulty, equipment) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (
                int(row['exercise_id']),
                row['exercise_name'].strip(),
                row['description'].strip(),
                row['type'].strip(),
                row['difficulty'].strip(),
                row['equipment'].strip()
            )
        )
print("Exercises imported.")

# Import muscles_exercised last, as it references both muscles and exercises
with open('data/Muscles exercised-Muscles exercised.csv', 'r') as f:
    reader = csv.DictReader(f)
    for row in reader:
        cur.execute(
            "INSERT INTO muscles_exercised (exercise_id, muscle_id, role) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
            (
                int(row['exercise_id']),
                int(row['muscle_id']),
                row['role'].strip()
            )
        )
print("Muscles exercised imported.")

conn.commit()
cur.close()
conn.close()
print("Done.")
