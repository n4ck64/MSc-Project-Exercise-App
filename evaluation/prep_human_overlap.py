"""Reshapes the answers the clinicians actually rated into ladder rows for the judge.

Judge-human agreement is only meaningful if both scored the SAME TEXT. The raters saw
`answers.jsonl`, generated 23 July; the ladder run regenerates rung 6 against a
pipeline that has changed by several hundred lines since. Judging the new outputs and
comparing them to verdicts on the old ones would report an agreement that was never
measured.

So the overlap set is the 10 form questions in both arms, exactly as rated, mapped
onto the ladder's rung numbering: base llama3.1 -> rung 1, the shipped pipeline of the
day -> rung 6.

    python evaluation/prep_human_overlap.py
    python evaluation/judge.py --ladder evaluation/human_overlap.jsonl \\
                              --out evaluation/judgements_overlap.jsonl
"""
import csv
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ANSWERS = os.path.join(HERE, "answers.jsonl")
KEY = os.path.join(HERE, "form_key.csv")
OUT = os.path.join(HERE, "human_overlap.jsonl")

# the ladder rung each historical arm corresponds to
ARM_RUNG = {"base": 1, "full": 6}


def main():
    with open(KEY, newline="") as f:
        form_items = {int(row["question_id"]): row for row in csv.DictReader(f)}

    with open(ANSWERS) as f:
        answers = [json.loads(line) for line in f if line.strip()]

    written = 0
    with open(OUT, "w") as out:
        for row in answers:
            if row["id"] not in form_items or row["arm"] not in ARM_RUNG:
                continue
            out.write(json.dumps({
                "set": "exercise",
                "id": row["id"],
                "rung": ARM_RUNG[row["arm"]],
                "arm_label": f"{row['arm']} (as rated by clinicians)",
                "persona": "sam",
                "tier": row["tier"],
                "question": row["question"],
                "answer": row["answer"],
                "context": None,          # not logged at the time; RAGAS cannot use these
                "form_item": int(form_items[row["id"]]["item"]),
            }) + "\n")
            written += 1

    print(f"wrote {written} rows to {os.path.basename(OUT)} "
          f"({len(form_items)} questions x {len(ARM_RUNG)} arms)")


if __name__ == "__main__":
    main()
