"""
Database WRITE operations for user-generated data.
"""

from datetime import date

from retrieval import (conn, cur, db_lock, get_food_id, resolve_food_name,
                       FOOD_MATCH_MAX_DISTANCE)

VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}
VALID_LIMIT_TYPES = {"target", "min", "max"}


def add_exercise_rating(user_id, exercise_id, difficulty):
    """Records a user's perceived difficulty for an exercise. Upsert on
    (user_id, exercise_id): a repeat rating replaces the previous one, so each
    user keeps at most one rating per exercise. 'difficulty' must be one of
    VALID_DIFFICULTIES."""
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(
            f"difficulty must be one of {sorted(VALID_DIFFICULTIES)}, got {difficulty!r}")
    with db_lock:
        cur.execute("""
                    INSERT INTO user_exercise_difficulty (user_id, exercise_id, difficulty)
                    VALUES (%s, %s, %s)
                    ON CONFLICT (user_id, exercise_id)
                    DO UPDATE SET difficulty = EXCLUDED.difficulty
                    """, (user_id, exercise_id, difficulty))
        conn.commit()


def clear_exercise_ratings(user_id):
    """Deletes all of a user's exercise ratings"""
    with db_lock:
        cur.execute(
            "DELETE FROM user_exercise_difficulty WHERE user_id = %s", (user_id,))
        conn.commit()


def log_food(user_id, grams, food_id=None, food_name=None, on_date=None):
    """Logs a food against a user's day, identified either by food_id or by name.
    'on_date' defaults to today. Returns the new entry, or None if nothing matched.
    Unlike the other writers here, this rolls back on failure: the connection is
    shared process-wide, so a poisoned transaction would take every later query
    with it, and the diary writes far more often than plans or ratings do."""
    if food_id is None:
        if food_name is None:
            raise ValueError("log_food needs either a food_id or a food_name")
        # thresholded, unlike the read-side callers: nearest-neighbour search
        # always returns its closest row, so an unbounded resolve would put a
        # food the user never ate in their diary rather than reporting no match
        resolved = resolve_food_name(
            food_name, max_distance=FOOD_MATCH_MAX_DISTANCE)
        food_id = get_food_id(food_name) or (
            get_food_id(resolved) if resolved else None)
    if food_id is None:
        return None
    with db_lock:
        try:
            # date.today() rather than Postgres CURRENT_DATE to avoid timezone shenanigans
            cur.execute("""
                        INSERT INTO food_log (user_id, food_id, grams, logged_on)
                        VALUES (%s, %s, %s, %s)
                        RETURNING log_id
                        """, (user_id, food_id, grams, on_date or date.today()))
            log_id = cur.fetchone()[0]
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return {"log_id": log_id, "food_id": food_id, "grams": grams}


def delete_log_entry(user_id, log_id):
    """Removes one logged food. Scoped by user_id as well as log_id so a user can
    only ever delete their own entries. Returns True if a row was actually
    deleted, False if the entry does not exist or belongs to someone else."""
    with db_lock:
        try:
            cur.execute("DELETE FROM food_log WHERE log_id = %s AND user_id = %s",
                        (log_id, user_id))
            deleted = cur.rowcount > 0
            conn.commit()
        except Exception:
            conn.rollback()
            raise
    return deleted


def set_nutrition_targets(user_id, targets):
    """Nothing calls this yet — the daily goal is currently the PHE baseline. It is
    the write path the cut/maintain/bulk goal flow will use."""
    for nutrient, (_, limit_type) in targets.items():
        if limit_type not in VALID_LIMIT_TYPES:
            raise ValueError(f"limit_type for {nutrient} must be one of "
                             f"{sorted(VALID_LIMIT_TYPES)}, got {limit_type!r}")
    with db_lock:
        try:
            for nutrient, (value, limit_type) in targets.items():
                cur.execute("""
                            INSERT INTO user_nutrition_targets (user_id, nutrient, value, limit_type)
                            VALUES (%s, %s, %s, %s)
                            ON CONFLICT (user_id, nutrient)
                            DO UPDATE SET value = EXCLUDED.value,
                                          limit_type = EXCLUDED.limit_type
                            """, (user_id, nutrient, value, limit_type))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def clear_nutrition_targets(user_id):
    """Drops a user's target overrides, reverting them to the PHE population
    guideline for their sex and age."""
    with db_lock:
        try:
            cur.execute(
                "DELETE FROM user_nutrition_targets WHERE user_id = %s", (user_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise


def save_plan(user_id, plan_name, exercises):
    """Persists a freshly-built plan for a user, replacing any existing one —
    plans.user_id is UNIQUE, so each user has exactly one active plan."""
    names = list({exercise["name"] for exercise in exercises})
    with db_lock:
        cur.execute(
            "SELECT exercise_name, exercise_id FROM exercises WHERE exercise_name = ANY(%s)",
            (names,))
        name_to_id = dict(cur.fetchall())

        cur.execute("""
                    INSERT INTO plans (plan_name, user_id)
                    VALUES (%s, %s)
                    ON CONFLICT (user_id) DO UPDATE SET plan_name = EXCLUDED.plan_name
                    RETURNING plan_id
                    """, (plan_name, user_id))
        plan_id = cur.fetchone()[0]

        cur.execute("DELETE FROM plan_exercises WHERE plan_id = %s", (plan_id,))
        for order, exercise in enumerate(exercises):
            exercise_id = name_to_id.get(exercise["name"])
            if exercise_id is None:
                continue  # shouldn't happen — plan_schema constrains names to retrieved candidates
            cur.execute("""
                        INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps, "order")
                        VALUES (%s, %s, %s, %s, %s, %s)
                        """, (plan_id, exercise_id, exercise["day"], exercise["sets"], exercise["reps"], order))
        conn.commit()


_EDITABLE_FIELDS = {"sets", "reps"}


def apply_plan_edits(user_id, edits):
    """Applies a batch of already-resolved plan edits (see pipelines.route_plan_edit)
    to a user's plan_exercises rows, as one transaction. Each edit dict, by op:
      - move_day:       {op, from_day, to_day}            — moves every exercise on from_day
      - move_exercise:  {op, plan_exercise_id, to_day}
      - relative_param: {op, plan_exercise_id, field, amount}  — amount is a signed delta
      - absolute_param: {op, plan_exercise_id, field, amount}  — amount is the target value
      - add_exercise:   {op, exercise_id, day, sets, reps}
      - remove_exercise:{op, plan_exercise_id}                 — deletes the row entirely
    Raises ValueError if the user has no plan to edit."""
    with db_lock:
        cur.execute('SELECT plan_id FROM plans WHERE user_id = %s', (user_id,))
        row = cur.fetchone()
        if row is None:
            raise ValueError("No plan exists for this user")
        plan_id = row[0]

        for edit in edits:
            operation = edit["op"]
            if operation == "move_day":
                cur.execute("""
                            UPDATE plan_exercises SET day = %s
                            WHERE plan_id = %s AND day = %s
                            """, (edit["to_day"], plan_id, edit["from_day"]))
            elif operation == "move_exercise":
                cur.execute("""
                            UPDATE plan_exercises SET day = %s
                            WHERE plan_exercise_id = %s AND plan_id = %s
                            """, (edit["to_day"], edit["plan_exercise_id"], plan_id))
            elif operation in ("relative_param", "absolute_param"):
                field = edit["field"]
                if field not in _EDITABLE_FIELDS:
                    raise ValueError(
                        f"field must be one of {_EDITABLE_FIELDS}, got {field!r}")
                if operation == "relative_param":
                    cur.execute(f"""
                                UPDATE plan_exercises SET {field} = {field} + %s
                                WHERE plan_exercise_id = %s AND plan_id = %s
                                """, (edit["amount"], edit["plan_exercise_id"], plan_id))
                else:
                    cur.execute(f"""
                                UPDATE plan_exercises SET {field} = %s
                                WHERE plan_exercise_id = %s AND plan_id = %s
                                """, (edit["amount"], edit["plan_exercise_id"], plan_id))
            elif operation == "remove_exercise":
                cur.execute("""
                            DELETE FROM plan_exercises
                            WHERE plan_exercise_id = %s AND plan_id = %s
                            """, (edit["plan_exercise_id"], plan_id))
            elif operation == "add_exercise":
                cur.execute(
                    'SELECT COALESCE(MAX("order"), -1) + 1 FROM plan_exercises WHERE plan_id = %s',
                    (plan_id,))
                next_order = cur.fetchone()[0]
                cur.execute("""
                            INSERT INTO plan_exercises (plan_id, exercise_id, day, sets, reps, "order")
                            VALUES (%s, %s, %s, %s, %s, %s)
                            """, (plan_id, edit["exercise_id"], edit["day"],
                                  edit.get("sets", 3), edit.get("reps", 10), next_order))
        conn.commit()
