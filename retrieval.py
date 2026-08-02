"""
All Postgres database retrieval functions live here
"""

from datetime import date
import getpass
import os
import threading

import ollama
import psycopg2

# to use the app, user must have Postgres installed on device and be logged in
# os module gets the authentication details below
conn = psycopg2.connect(
    dbname=os.environ.get("REFIT_DB_NAME", "exercise_database"),
    user=os.environ.get("REFIT_DB_USER", getpass.getuser()),
)
cur = conn.cursor()
db_lock = threading.RLock()


def retrieve_exercises(query, top_k=3, target_muscle_id=None, injured_muscle_id=None,
                       equipment=None):
    """Queries the database to retrieve the top_k most relevant exercises
    based on the user's input and the corresponding generated embedding.
    Optionally constrained to a target muscle, a set of allowed equipment,
    and/or excluding an injured muscle"""

    response = ollama.embed(model="nomic-embed-text", input=f"search_query: {query}")\

    embedding = response.embeddings[0]

    conditions, params = [], []

    if target_muscle_id:
        conditions.append("""exercise_id IN (
        SELECT exercise_id FROM muscles_exercised
        WHERE muscle_id = ANY(%s) AND role = 'Primary')""")
        params.append(target_muscle_id)

    if equipment:
        conditions.append("equipment = ANY(%s)")
        params.append(equipment)

    if injured_muscle_id:
        conditions.append("""exercise_id NOT IN (
            SELECT exercise_id FROM muscles_exercised WHERE muscle_id = ANY(%s))""")
        params.append(injured_muscle_id)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with db_lock:
        cur.execute(f"""
        SELECT exercise_id, exercise_name, description, type, difficulty, equipment
        FROM exercises
        {where}
        ORDER BY embedding <=> %s::vector
        LIMIT %s
        """, params + [embedding, top_k])

        rows = cur.fetchall()

    # if the target-muscle filter matched nothing, drop it but keep the equipment
    # constraint (the user still cares which kit they have) and search again
    if not rows and target_muscle_id:
        return retrieve_exercises(query, top_k=top_k, injured_muscle_id=injured_muscle_id,
                                  equipment=equipment)

    results = []
    for ex_id, name, description, type_, difficulty, equipment in rows:
        m = _muscles_for_exercise(ex_id)
        results.append(
            f"Exercise: {name}\n"
            f"Type: {type_}\n"
            f"Difficulty: {difficulty}\n"
            f"Equipment: {equipment}\n"
            f"Muscles — Primary: {m['Primary']} | Secondary: {m['Secondary']} | Stabilisers: {m['Stabiliser']}\n"
            f"Description: {description}")
    return "\n\n".join(results)


def _muscles_for_exercise(exercise_id):
    """Returns an exercise's worked muscles grouped by role (Primary, Secondary,
    Stabiliser) as display strings, for grounding the answerer and reviewer."""
    with db_lock:
        cur.execute("""
                    SELECT me.role, string_agg(m.muscle_name, ', ' ORDER BY m.muscle_name)
                    FROM muscles_exercised me
                    JOIN muscles m ON m.muscle_id = me.muscle_id
                    WHERE me.exercise_id = %s
                    GROUP BY me.role
                    """, (exercise_id,))

        grouped = {"Primary": "none listed",
                   "Secondary": "none listed", "Stabiliser": "none listed"}
        # default values as none listed until appended

        for role, names in cur.fetchall():
            grouped[role] = names
    return grouped


def retrieve_exercise_names(description, top_k=3):
    """Queries the database to retrieve the three most relevant exercises
    based on the provided description and the corresponding generated embedding.
    This function is only used for the video analysis."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {description}")
    embedding = response.embeddings[0]
    with db_lock:
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
    with db_lock:
        cur.execute("""
                    SELECT description
                    FROM exercises
                    WHERE exercise_name ILIKE %s
                    """, (name,))
        result = cur.fetchone()
    if result is None:
        return None
    return result[0]


def retrieve_foods(query, top_k=3):
    """Queries the database to retrieve the most relevant foods
    based on the user's input, returning their key macros per 100g of food.
    Used by the nutrition talk pipeline."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT food_name, kcal, protein_g, fat_g, carb_g, total_sugars_g, fibre_nsp_g
                    FROM foods
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        rows = cur.fetchall()

    def fmt(value, unit):
        # CoFID leaves some nutrients unmeasured (stored as NULL).
        return f"{value}{unit}" if value is not None else "N/A"

    results = []
    for name, kcal, protein, fat, carb, sugars, fibre in rows:
        results.append(
            f"Food: {name} (per 100g)\n"
            f"Energy: {fmt(kcal, ' kcal')} | Protein: {fmt(protein, 'g')} | "
            f"Fat: {fmt(fat, 'g')} | Carbohydrate: {fmt(carb, 'g')} | "
            f"Sugars: {fmt(sugars, 'g')} | Fibre: {fmt(fibre, 'g')}")
    return "\n\n".join(results)


def resolve_food_name(query, top_k=1):
    """Maps the lay food name (e.g. "chicken breast") to the nearest
    match in the database. This allows for nutrition RAG functions to
    retrieve data without returning None"""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT food_name
                    FROM foods
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        row = cur.fetchone()
    return row[0] if row else None


def retrieve_nutrient_targets(sex, age):
    """Returns the UK daily dietary guideline values (PHE 2016) for a user of
    the given sex ('M'/'F') and age, as a {nutrient: (value, limit_type)} dict.
    limit_type is 'target', 'min' (at least) or 'max' (less than)."""
    with db_lock:
        cur.execute("""
                    SELECT nutrient, value, limit_type
                    FROM nutrient_reference
                    WHERE sex = %s AND %s BETWEEN age_min AND age_max
                    """, (sex, age))
        return {nutrient: (value, limit_type) for nutrient, value, limit_type in cur.fetchall()}


def get_user_sex_age(user_id):
    """Returns (sex, age_in_years) for a user, age derived from date_of_birth.
    Returns None if the user or their date of birth is missing."""
    with db_lock:
        cur.execute(
            'SELECT gender, date_of_birth FROM "user" WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
    if row is None or row[1] is None:
        return None
    gender, dob = row
    today = date.today()
    age = today.year - dob.year - \
        ((today.month, today.day) < (dob.month, dob.day))
    return gender, age


def get_food_macros(food_name, grams=100):
    """Returns a food's macros scaled to 'grams', keyed to match the
    nutrient_reference nutrients (looked up by name, case-insensitive)"""

    with db_lock:
        cur.execute("""
                    SELECT kcal, protein_g, fat_g, carb_g, total_sugars_g,
                           COALESCE(fibre_aoac_g, fibre_nsp_g)
                    FROM foods
                    WHERE food_name ILIKE %s
                    ORDER BY length(food_name)
                    LIMIT 1
                    """, (food_name,))
        row = cur.fetchone()
    if row is None:
        return None
    kcal, protein, fat, carb, sugars, fibre = row
    factor = grams / 100.0
    scaled = {"energy_kcal": kcal, "protein_g": protein, "fat_g": fat,
              "carb_g": carb, "free_sugars_g": sugars, "fibre_g": fibre}
    return {k: round(v * factor, 1) for k, v in scaled.items() if v is not None}


def compute_macro_gaps(sex, age, consumed):
    """Compares a dict of consumed macros against the user's daily guideline and
    returns, per nutrient, the amount consumed, the target, its limit_type, and
    'remaining' (target - consumed): for 'target'/'min' how much is left to go;
    for 'max' the headroom left, where a negative value means the limit is
    exceeded."""
    targets = retrieve_nutrient_targets(sex, age)
    result = {}
    for nutrient, (target, limit_type) in targets.items():
        amount = consumed.get(nutrient)
        if amount is None:
            continue
        result[nutrient] = {
            "consumed": amount,
            "target": target,
            "limit_type": limit_type,
            "remaining": round(target - amount, 1),
        }
    return result


def daily_gaps_for_food(user_id, food_name, grams=100):
    """End-to-end: how eating 'grams' of 'food_name' contributes toward a user's
    daily UK dietary guideline. Returns a readable summary, or a note if the
    user/date of birth or the food is missing."""
    context = get_user_sex_age(user_id)
    if context is None:
        return "No user record or date of birth on file."
    sex, age = context
    consumed = get_food_macros(food_name, grams)
    if consumed is None:
        return f"No food matching '{food_name}' found."
    gaps = compute_macro_gaps(sex, age, consumed)

    labels = {"energy_kcal": "Energy (kcal)", "protein_g": "Protein (g)",
              "fat_g": "Fat (g)", "carb_g": "Carbohydrate (g)",
              "free_sugars_g": "Sugars (g)", "fibre_g": "Fibre (g)"}
    lines = [f"{grams}g of {food_name} vs daily guideline ({sex}, age {age}):"]
    for nutrient, g in gaps.items():
        if g["limit_type"] == "max":
            note = (f"{abs(g['remaining'])} over limit" if g["remaining"] < 0
                    else f"{g['remaining']} headroom left")
        else:
            note = f"{g['remaining']} to go" if g["remaining"] > 0 else "target met"
        lines.append(f"  {labels.get(nutrient, nutrient)}: {g['consumed']} of "
                     f"{g['target']} ({g['limit_type']}) -> {note}")
    return "\n".join(lines)


def list_exercises():
    """Returns a list of dictionaries of all exercises within the database
    for searching and browsing within the 'Exercises' tab"""
    with db_lock:
        cur.execute("""
        SELECT exercise_id, exercise_name, description, type, difficulty, equipment
        FROM exercises
        ORDER BY exercise_name
        """)

        rows = cur.fetchall()

        exercises = []

        for ex_id, name, description, type_, difficulty, equipment in rows:
            exercises.append({
                "id": ex_id,
                "name": name,
                "description": description,
                "type": type_,
                "difficulty": difficulty,
                "equipment": equipment,
                "muscles": _muscles_for_exercise(ex_id)
            })
    return exercises


def get_user_plan(user_id):
    """Returns a user's current plan as {"exercises": [{name, day, sets, reps}, ...]},
    ordered the same way it was built, or None if they have no plan yet."""
    with db_lock:
        cur.execute("""
                    SELECT e.exercise_name, pe.day, pe.sets, pe.reps
                    FROM plans p
                    JOIN plan_exercises pe ON pe.plan_id = p.plan_id
                    JOIN exercises e ON e.exercise_id = pe.exercise_id
                    WHERE p.user_id = %s
                    ORDER BY pe."order"
                    """, (user_id,))
        rows = cur.fetchall()
    if not rows:
        return None
    return {"exercises": [
        {"name": name, "day": day, "sets": sets, "reps": reps}
        for name, day, sets, reps in rows
    ]}


def get_user_plan_rows(user_id):
    """Like get_user_plan, but includes plan_exercise_id/exercise_id — used by
    the plan-edit pipeline(pipelines.route_plan_edit) to target a specific row
    for a move/param edit. Plans.tsx doesn't need these ids, hence the separate
    function."""
    with db_lock:
        cur.execute("""
                    SELECT pe.plan_exercise_id, e.exercise_id, e.exercise_name, pe.day, pe.sets, pe.reps
                    FROM plans p
                    JOIN plan_exercises pe ON pe.plan_id = p.plan_id
                    JOIN exercises e ON e.exercise_id = pe.exercise_id
                    WHERE p.user_id = %s
                    ORDER BY pe."order"
                    """, (user_id,))
        rows = cur.fetchall()
    return [{"plan_exercise_id": plan_id, "exercise_id": exercise_id, "name": name,
             "day": day, "sets": sets, "reps": reps}
            for plan_id, exercise_id, name, day, sets, reps in rows]


def get_exercise_id(exercise_name):
    """Exact(case-insensitive) exercise_name -> exercise_id lookup. Used to
    resolve an add_exercise plan edit after resolve_exercise_name finds the
    canonical name."""
    with db_lock:
        cur.execute(
            "SELECT exercise_id FROM exercises WHERE exercise_name ILIKE %s LIMIT 1",
            (exercise_name,))
        row = cur.fetchone()
    return row[0] if row else None


def resolve_exercise_name(query, top_k=1):
    """Maps a free-text exercise name(e.g. "lunges") to the closest canonical
    exercise_name via embedding search. Used to resolve an add_exercise plan edit
    to a real exercise_id. Returns the best-matching exercise_name, or None if the table is empty."""

    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    with db_lock:
        cur.execute("""
                    SELECT exercise_name
                    FROM exercises
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))
        row = cur.fetchone()
    return row[0] if row else None


def get_exercise_ratings(user_id, exercise_id=None):
    """Returns a user's self-reported exercise difficulty ratings as an
    {exercise_id: difficulty} dict. Pass exercise_id to fetch a single one
    (dict with 0 or 1 entry); omit it for all of the user's ratings."""
    with db_lock:
        if exercise_id is None:
            cur.execute("""
                        SELECT exercise_id, difficulty
                        FROM user_exercise_difficulty
                        WHERE user_id = %s
                        """, (user_id,))
        else:
            cur.execute("""
                        SELECT exercise_id, difficulty
                        FROM user_exercise_difficulty
                        WHERE user_id = %s AND exercise_id = %s
                        """, (user_id, exercise_id))
        return {ex_id: difficulty for ex_id, difficulty in cur.fetchall()}
