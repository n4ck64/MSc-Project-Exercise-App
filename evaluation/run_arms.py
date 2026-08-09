"""
Runs the 20 eval questions through both arms and writes the answers to JSONL.

    base  — raw llama3.1, no system prompt, no RAG, no reviewer, no rewriter.
            The "nothing" end of the ablation ladder.
    full  — run_chat_pipeline: classify -> RAG -> refit-dpo answerer -> qwen
            reviewer -> refit-dpo rewriter. The "everything" end.

Both arms receive the identical persona-prefixed prompt, so the pipeline is the
only variable. Memory is cleared between every question: the pipeline keeps global
chat history and plan slots, and without the reset a question that classifies as
PLAN_* would trap every subsequent question in the plan loop.

Append-only and resumable — a crashed run is re-run with the same command and picks
up where it stopped.

    python evaluation/run_arms.py              # both arms, all 20
    python evaluation/run_arms.py --arm base   # one arm only
    python evaluation/run_arms.py --only-form  # just the 10 form questions
"""
import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from ollama import chat                                       # noqa: E402
from memory import Memory                                     # noqa: E402
from pipelines import run_chat_pipeline                       # noqa: E402
from questions import QUESTIONS, with_persona                 # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "answers.jsonl")

# the pipeline yields these as UI progress markers, not as answer text
# (mirrors STATUS_TOKENS in refit/src/pages/Chat.tsx)
STATUS_TOKENS = {"Thinking...", "Reviewing...", "Analysing...",
                 "Processing...", "Hungry...", "Uploading..."}


def run_base(prompt):
    """The unaided baseline: base llama3.1, no system prompt at all. Deliberately
    bare — giving it ReFit's system prompt would make this a fine-tuning ablation
    rather than a whole-system one."""
    resp = chat("llama3.1",
                messages=[{"role": "user", "content": prompt}],
                options={"temperature": 0.7, "num_predict": 8192, "num_ctx": 8192},
                stream=False)
    return resp.message.content


def run_full(prompt):
    """The full ReFit pipeline, drained to a single string."""
    Memory.clear()
    parts = [token for token in run_chat_pipeline(prompt)
             if token not in STATUS_TOKENS]
    return "".join(parts).strip()


ARMS = {"base": run_base, "full": run_full}


def already_done(path):
    """(question_id, arm) pairs already written, so a re-run resumes."""
    if not os.path.exists(path):
        return set()
    done = set()
    with open(path) as f:
        for line in f:
            if line.strip():
                row = json.loads(line)
                done.add((row["id"], row["arm"]))
    return done


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--arm", choices=list(ARMS), help="run one arm only")
    parser.add_argument("--only-form", action="store_true",
                        help="only the 10 questions sampled into the clinician form")
    args = parser.parse_args()

    questions = [q for q in QUESTIONS if q["in_form"]] if args.only_form else QUESTIONS
    arms = [args.arm] if args.arm else list(ARMS)
    done = already_done(OUT)

    todo = [(q, arm) for q in questions for arm in arms if (q["id"], arm) not in done]
    print(f"{len(todo)} to run ({len(done)} already in {os.path.basename(OUT)})")

    for question, arm in todo:
        prompt = with_persona(question["text"])
        print(f"[{question['id']:>2}/{arm:<4}] tier {question['tier']} ... ", end="", flush=True)

        started = time.time()
        try:
            answer = ARMS[arm](prompt)
        except Exception as exc:                    # one bad call shouldn't end the run
            print(f"FAILED: {exc}")
            continue
        elapsed = round(time.time() - started, 1)

        with open(OUT, "a") as f:
            f.write(json.dumps({
                "id": question["id"],
                "tier": question["tier"],
                "in_form": question["in_form"],
                "question": question["text"],
                "arm": arm,
                "answer": answer,
                "seconds": elapsed,
                "words": len(answer.split()),
            }) + "\n")

        print(f"{elapsed}s, {len(answer.split())} words")


if __name__ == "__main__":
    main()
