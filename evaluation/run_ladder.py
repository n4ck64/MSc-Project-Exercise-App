"""Runs the question banks through every rung of the ablation ladder.

Every rung goes through `run_chat_pipeline` itself, varying only an ArmConfig, so the
arms differ by configuration rather than by reimplementation. Each row records the
config that produced it, making the one-variable-per-rung claim auditable from the
data file rather than from the commit history.

Running this requires `run_chat_pipeline` to accept an `arm` argument. That injection
point is instrumentation for the ablation and is not part of the shipped pipeline, so
this harness runs against an instrumented build. T

Retrieved context is persisted alongside every answer. RAGAS faithfulness needs the
exact context an answer was grounded on, and that cannot be reconstructed afterwards —
a run without it would have to be thrown away and repeated.

Append-only and resumable: re-run the same command after a crash and it picks up where
it stopped.

    python evaluation/run_ladder.py                    # everything
    python evaluation/run_ladder.py --set exercise     # one bank
    python evaluation/run_ladder.py --rung 6           # one rung
    python evaluation/run_ladder.py --dry-run          # show the plan, generate nothing
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from memory import Memory                                        # noqa: E402
from pipelines import run_chat_pipeline                          # noqa: E402
from arms import (EXERCISE_LADDER, NUTRITION_LADDER, PERSONA_ARMS,   # noqa: E402
                  EXERCISE_PREDECESSOR, NUTRITION_PREDECESSOR, verify_ladder)
from questions import (QUESTIONS, NUTRITION_QUESTIONS, PERSONA_QUESTIONS,  # noqa: E402
                       USED_PERSONAS, PERSONA, with_persona)

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ladder.jsonl")

# Progress markers the pipeline yields for the UI. They are not answer text, and one
# leaking into a judged answer would corrupt both the readability metric and the word count
STATUS_TOKENS = {
    "Commencing...", "Classifying User Query...", "Thinking...", "Reviewing...",
    "Analysing...", "Processing...", "Hungry...", "Uploading...", "Making Plan...",
}

# sentinel tokens carry structured data to the frontend, not prose
SENTINEL_PREFIXES = ("EXERCISES:", "CHOICES:")

# Intents whose pipelines return a clarifying question or a built plan rather than
# advice. An eval question routed here has not been answered, so its text cannot be
# scored for answer quality — the score would be measuring the intent classifier.
MISROUTE_INTENTS = {"PLAN_GENERAL", "PLAN_INJURY", "PLAN_EDIT"}


def drain(prompt, user_id, arm):
    """One pipeline run, flattened to a single answer string.

    Memory is cleared first: chat history and plan slots are process-global, so
    without the reset a question that classifies as PLAN_* would trap every question
    after it in the plan loop, and prior answers would leak into later context.
    """
    Memory.clear()
    parts = []
    for token in run_chat_pipeline(prompt, user_id=user_id, arm=arm):
        if token in STATUS_TOKENS or token.startswith(SENTINEL_PREFIXES):
            continue
        parts.append(token)
    return ("".join(parts).strip(), Memory.last_rag_context, Memory.last_intent)


def build_plan(args):
    """Every (row-key, prompt, arm) the run should produce."""
    plan = []

    if args.set in (None, "exercise"):
        for rung, (label, arm) in sorted(EXERCISE_LADDER.items()):
            for question in QUESTIONS:
                plan.append({
                    "set": "exercise", "id": question["id"], "rung": rung,
                    "arm_label": label, "persona": "sam", "user_id": 1,
                    "tier": question["tier"],
                    "retrieval_dependent": question["retrieval_dependent"],
                    "in_form": question["in_form"],
                    "question": question["text"],
                    "prompt": with_persona(question["text"]),
                    "arm": arm,
                })

    if args.set in (None, "nutrition"):
        for rung, (label, arm) in sorted(NUTRITION_LADDER.items()):
            for question in NUTRITION_QUESTIONS:
                plan.append({
                    "set": "nutrition", "id": question["id"], "rung": rung,
                    "arm_label": label, "persona": "sam", "user_id": 1,
                    "tier": question["tier"], "tool": question["tool"],
                    "retrieval_dependent": question["tool"] != "none",
                    "question": question["text"],
                    "prompt": with_persona(question["text"]),
                    "arm": arm,
                })

    if args.set in (None, "persona"):
        for rung, (label, arm) in sorted(PERSONA_ARMS.items()):
            for name, persona in sorted(SWEEP_PERSONAS.items()):
                for question in PERSONA_QUESTIONS:
                    plan.append({
                        "set": "persona", "id": question["id"], "rung": rung,
                        "arm_label": label, "persona": name,
                        "user_id": persona["user_id"],
                        "question": question["text"],
                        "prompt": with_persona(question["text"], persona["text"]),
                        "arm": arm,
                    })

    if args.rung:
        plan = [row for row in plan if row["rung"] == args.rung]
    return plan


def row_key(row):
    """What makes a row unique, for resume. Persona is part of it: the same question
    at the same rung is a different data point for a different persona."""
    return (row["set"], row["id"], row["rung"], row["persona"])


def already_done(path):
    """Rows already written, so a resumed run skips them.

    A trailing partial line is tolerated: if the machine dies mid-write the last
    record can be truncated, and refusing to parse it would make an interrupted run
    unresumable — the one situation resume exists for. The partial row is dropped and
    regenerated.
    """
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path) as f:
        for number, line in enumerate(f, 1):
            if not line.strip():
                continue
            try:
                done.add(row_key(json.loads(line)))
            except json.JSONDecodeError:
                print(f"  ignoring unreadable line {number} of "
                      f"{os.path.basename(path)} (likely an interrupted write)")
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--set", choices=["exercise", "nutrition", "persona"],
                        help="run one bank only")
    parser.add_argument("--rung", type=int, help="run one rung only")
    parser.add_argument("--dry-run", action="store_true",
                        help="print what would run, generate nothing")
    parser.add_argument("--out", default=OUT)
    args = parser.parse_args()

    # a ladder that changed two things at once would invalidate every delta computed
    # from the run, so refuse to generate against one
    verify_ladder(EXERCISE_LADDER, "exercise", EXERCISE_PREDECESSOR)
    verify_ladder(NUTRITION_LADDER, "nutrition", NUTRITION_PREDECESSOR)

    plan = build_plan(args)
    done = already_done(args.out)
    todo = [row for row in plan if row_key(row) not in done]

    print(f"{len(plan)} rows in plan, {len(done)} already done, {len(todo)} to run")
    if args.dry_run:
        for row in todo[:10]:
            print(f"  {row['set']:<9} rung {row['rung']} {row['persona']:<7} "
                  f"q{row['id']}  {row['question'][:56]}")
        if len(todo) > 10:
            print(f"  ... and {len(todo) - 10} more")
        return

    started_all = time.time()
    for index, row in enumerate(todo, 1):
        arm = row.pop("arm")
        print(f"[{index:>3}/{len(todo)}] {row['set']:<9} rung {row['rung']} "
              f"{row['persona']:<7} q{row['id']} ... ", end="", flush=True)

        started = time.time()
        try:
            answer, context, intent = drain(
                row.pop("prompt"), row["user_id"], arm)
        except Exception as exc:            # one bad call must not end a 2-hour run
            print(f"FAILED: {exc}")
            continue

        row.update({
            # the exact config that produced this answer
            "arm": vars(arm),
            "answer": answer,
            "context": context,
            "intent": intent,
            "misrouted": intent in MISROUTE_INTENTS,
            "seconds": round(time.time() - started, 1),
            "words": len(answer.split()),
        })

        with open(args.out, "a") as f:
            f.write(json.dumps(row) + "\n")

        print(f"{row['seconds']}s, {row['words']} words"
              + (f"  MISROUTED -> {intent}" if row["misrouted"] else ""))

    print(f"done in {(time.time() - started_all) / 60:.1f} min")


if __name__ == "__main__":
    main()
