"""
Database WRITE operations for user-generated data.

Kept separate from retrieval.py (which is read-only) but reuses its shared
connection, cursor and lock, so every DB access — read or write — goes through
the same serialised path rather than opening a second connection.

For now this is exercise ratings only; profile/injury writes join here once
field-level encryption lands.
"""

from retrieval import conn, cur, db_lock

# Matches the vocabulary already stored in the exercises table (and the
# varchar(6) width of user_exercise_difficulty.difficulty — "Medium" is 6 chars).
VALID_DIFFICULTIES = {"Easy", "Medium", "Hard"}


def add_exercise_rating(user_id, exercise_id, difficulty):
    """Records a user's perceived difficulty for an exercise. Upsert on
    (user_id, exercise_id): a repeat rating replaces the previous one, so each
    user keeps at most one rating per exercise. `difficulty` must be one of
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
    """Deletes all of a user's exercise ratings. Used by the /clear debug reset
    so ratings don't leak across test sessions."""
    with db_lock:
        cur.execute(
            "DELETE FROM user_exercise_difficulty WHERE user_id = %s", (user_id,))
        conn.commit()
