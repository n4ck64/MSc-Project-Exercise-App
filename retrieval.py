"""
All database retrieval functions live here
"""

from datetime import date

import ollama
import psycopg2

conn = psycopg2.connect(dbname="exercise_database", user="nikolaytinev")
cur = conn.cursor()


def retrieve_exercises(query, top_k=3, injured_muscle_id=None):
    """Queries the database to retrieve the three most relevant exercises
    based on the user's input and the corresponding generated embedding"""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
    if injured_muscle_id:
        cur.execute("""
                    SELECT exercise_id, exercise_name, description, type, difficulty, equipment
                    FROM exercises
                    WHERE exercise_id NOT IN (
                        SELECT exercise_id FROM muscles_exercised WHERE muscle_id = %s
                        )
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (injured_muscle_id, embedding, top_k))
    else:
        cur.execute("""
                    SELECT exercise_id, exercise_name, description, type, difficulty, equipment
                    FROM exercises
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s
                    """, (embedding, top_k))

    rows = cur.fetchall()
    results = []
    for ex_id, name, description, type_, difficulty, equipment in rows:
        m = _muscles_for_exercise(ex_id)
        results.append(
            f"Exercise: {name}\n"
            f"Type: {type_} | Difficulty: {difficulty} | Equipment: {equipment}\n"
            f"Muscles — Primary: {m['Primary']} | Secondary: {m['Secondary']} | Stabilisers: {m['Stabiliser']}\n"
            f"Description: {description}")
    return "\n\n".join(results)


def _muscles_for_exercise(exercise_id):
    """Returns an exercise's worked muscles grouped by role (Primary, Secondary,
    Stabiliser) as display strings, for grounding the answerer and reviewer."""
    cur.execute("""
                SELECT me.role, string_agg(m.muscle_name, ', ' ORDER BY m.muscle_name)
                FROM muscles_exercised me
                JOIN muscles m ON m.muscle_id = me.muscle_id
                WHERE me.exercise_id = %s
                GROUP BY me.role
                """, (exercise_id,))
    grouped = {"Primary": "none listed",
               "Secondary": "none listed", "Stabiliser": "none listed"}
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


def retrieve_foods(query, top_k=3):
    """Queries the database to retrieve the most relevant foods
    based on the user's input, returning their key macros per 100g of food.
    Used by the nutrition talk pipeline."""
    response = ollama.embed(model="nomic-embed-text",
                            input=f"search_query: {query}")
    embedding = response.embeddings[0]
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


def retrieve_nutrient_targets(sex, age):
    """Returns the UK daily dietary guideline values (PHE 2016) for a user of
    the given sex ('M'/'F') and age, as a {nutrient: (value, limit_type)} dict.
    limit_type is 'target', 'min' (at least) or 'max' (less than)."""
    cur.execute("""
                SELECT nutrient, value, limit_type
                FROM nutrient_reference
                WHERE sex = %s AND %s BETWEEN age_min AND age_max
                """, (sex, age))
    return {nutrient: (value, limit_type) for nutrient, value, limit_type in cur.fetchall()}


def get_user_sex_age(user_id):
    """Returns (sex, age_in_years) for a user, age derived from date_of_birth.
    Returns None if the user or their date of birth is missing."""
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
    """Returns a food's macros scaled to `grams`, keyed to match the
    nutrient_reference nutrients (looked up by name, case-insensitive).
    Proxies to be aware of: the foods table stores TOTAL sugars, not free
    sugars, so free_sugars_g is an over-estimate; and there is no
    saturated-fat column, so satfat_g is not returned."""
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
    `remaining` (target - consumed): for 'target'/'min' how much is left to go;
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
