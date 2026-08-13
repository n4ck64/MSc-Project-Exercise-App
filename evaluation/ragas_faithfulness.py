"""RAGAS faithfulness over the exercise ladder's RAG rungs.

Scoped to rungs 3/4/6 (the only rungs with retrieval switched on) on the 5 questions 
tagged retrieval_dependent in questions.py, excluding anything misrouted. 

Faithfulness only needs an LLM (it checks each claim in the answer against the
retrieved context), not an embedding model, so no embeddings config here.

The judge LLM is the same Claude Sonnet 5 via DeepInfra that judge.py uses --
reused as-is, no second account or key.

    export LLM_API_KEY=...
    pip install "ragas==0.1.22" langchain-openai datasets
    python evaluation/ragas_faithfulness.py --dry-run     # show the 15 rows, call nothing
    python evaluation/ragas_faithfulness.py                # full pass
"""
import argparse
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))

LADDER = os.path.join(HERE, "ladder.jsonl")
OUT = os.path.join(HERE, "ragas_faithfulness.jsonl")

MODEL = "anthropic/claude-sonnet-5"
PROVIDER = "https://api.deepinfra.com/v1/openai"
TEMPERATURE = 0.1

TARGET_SET = "exercise"
TARGET_RUNGS = (3, 4, 6)

RUNG_LABELS = {3: "+ RAG", 4: "+ ReFit prompts",
               6: "fine-tuned model + everything (shipped)"}


def load_rows(path):
    """The 15-row slice faithfulness can actually be scored against: retrieval
    switched on, retrieval-dependent question, answered (not misrouted)."""
    with open(path) as f:
        rows = [json.loads(line) for line in f if line.strip()]

    rows = [row for row in rows
            if row["set"] == TARGET_SET
            and row["rung"] in TARGET_RUNGS
            and row.get("retrieval_dependent")
            and not row.get("misrouted")]

    missing_context = [row for row in rows if not row.get("context")]
    if missing_context:
        raise SystemExit(
            f"{len(missing_context)} row(s) tagged retrieval_dependent have no "
            f"logged context -- faithfulness cannot be scored without regenerating "
            f"them. First offender: {missing_context[0]['set']} q{missing_context[0]['id']} "
            f"rung {missing_context[0]['rung']}")
    return rows


def contexts_for(row):
    """retrieval.py joins retrieved exercises with a blank line between each one
    (retrieve_exercises' `"\\n\\n".join(results)`); splitting on the same separator
    recovers the individual chunks RAGAS scores claims against."""
    return [chunk for chunk in row["context"].split("\n\n") if chunk.strip()]


def build_dataset(rows):
    from datasets import Dataset
    return Dataset.from_dict({
        "question": [row["question"] for row in rows],
        "answer": [row["answer"] for row in rows],
        "contexts": [contexts_for(row) for row in rows],
    })


def build_llm():
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise SystemExit("LLM_API_KEY not set -- this runs on a paid API.")

    from langchain_openai import ChatOpenAI
    from ragas.llms import LangchainLLMWrapper

    chat = ChatOpenAI(model=MODEL, openai_api_base=PROVIDER,
                      openai_api_key=key, temperature=TEMPERATURE)
    return LangchainLLMWrapper(chat)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--ladder", default=LADDER)
    parser.add_argument("--out", default=OUT)
    parser.add_argument("--dry-run", action="store_true",
                        help="show the rows that would be scored and exit")
    args = parser.parse_args()

    rows = load_rows(args.ladder)

    if args.dry_run:
        for row in rows:
            print(f"  {row['set']} q{row['id']} rung {row['rung']} "
                  f"({RUNG_LABELS[row['rung']]}) -- {len(contexts_for(row))} context chunks")
        print(f"\n({len(rows)} rows would be scored)")
        return

    from ragas import evaluate
    from ragas.metrics import faithfulness

    dataset = build_dataset(rows)
    llm = build_llm()

    result = evaluate(dataset, metrics=[faithfulness], llm=llm)
    scores = result.to_pandas()["faithfulness"].tolist()

    with open(args.out, "w") as f:
        for row, score in zip(rows, scores):
            f.write(json.dumps({
                "set": row["set"], "id": row["id"], "rung": row["rung"],
                "arm_label": row.get("arm_label"), "faithfulness": score,
            }) + "\n")

    print(f"wrote {len(rows)} scores to {args.out}\n")
    by_rung = {}
    for row, score in zip(rows, scores):
        by_rung.setdefault(row["rung"], []).append(score)

    print(f"{'rung':<5}{'n':>4}   faithfulness   label")
    print("-" * 55)
    for rung in TARGET_RUNGS:
        vals = by_rung.get(rung, [])
        mean = statistics.mean(vals) if vals else float("nan")
        print(f"{rung:<5}{len(vals):>4}   {mean:>10.2f}   {RUNG_LABELS[rung]}")


if __name__ == "__main__":
    main()
