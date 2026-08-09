"""
Unblinds and analyses the pharmacist rater form responses (human_eval_responses.csv,
exported from the Google Form built by build_form.py) against form_key.csv.

    python evaluation/analyze_human_eval.py

Prints per-item and aggregate win/loss tables for the full pipeline vs base
llama3.1, plus inter-rater agreement (Fleiss' kappa) per question type.
"""
import csv
import os
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
KEY = os.path.join(HERE, "form_key.csv")
RESPONSES = os.path.join(HERE, "human_eval_responses.csv")
REPORT = os.path.join(HERE, "human_eval_results.md")

QUESTIONS = [
    "dangerous_advice",
    "factual_accuracy",
    "referral",
    "overall_trust",
    "comment",
]

# per question type, which raw answer strings map to which arm
ARM_WORDS = {"Response A", "Response B"}
NEUTRAL_LABELS = {
    "dangerous_advice": {"Neither", "Both equally concerning"},
    "factual_accuracy": {"Both are accurate", "Both have errors", "Not sure"},
    "referral": {"Both appropriate", "Both inappropriate", "Not sure"},
    "overall_trust": {"No preference"},
}


def load_key():
    with open(KEY, newline="") as f:
        return {int(row["item"]): row for row in csv.DictReader(f)}


def load_responses():
    with open(RESPONSES, newline="", encoding="utf-8") as f:
        rows = list(csv.reader(f))
    raters = []
    for row in rows[1:]:
        if not row or not row[0].strip():
            continue
        raters.append(row)
    return raters


def unblind(raw_answer, item_key, question_type):
    """Map a raw 'Response A'/'Response B' answer to 'full'/'base'; pass through
    neutral labels unchanged."""
    if raw_answer == "Response A":
        return item_key["response_A"]
    if raw_answer == "Response B":
        return item_key["response_B"]
    return raw_answer


def fleiss_kappa(item_answers, categories):
    """item_answers: list of Counter (category -> count) per item, all same n raters."""
    n_items = len(item_answers)
    n_raters = sum(item_answers[0].values())
    if n_items == 0 or n_raters < 2:
        return None
    p_j = {c: 0 for c in categories}
    P_i = []
    for counts in item_answers:
        total = sum(counts.values())
        if total != n_raters:
            return None  # missing data breaks the simple formula
        agree = sum(k * (k - 1) for k in counts.values())
        P_i.append(agree / (n_raters * (n_raters - 1)))
        for c in categories:
            p_j[c] += counts.get(c, 0)
    for c in categories:
        p_j[c] /= (n_items * n_raters)
    P_bar = sum(P_i) / n_items
    P_e = sum(p ** 2 for p in p_j.values())
    if P_e == 1:
        return 1.0
    return (P_bar - P_e) / (1 - P_e)


def main():
    key = load_key()
    raters = load_responses()
    n_raters = len(raters)
    n_items = len(key)
    print(f"{n_raters} raters, {n_items} items\n")

    # unblinded[question_type][item] = Counter over {"full","base",<neutral labels>}
    unblinded = {q: defaultdict(Counter) for q in QUESTIONS if q != "comment"}
    comments = defaultdict(list)

    for rater_row in raters:
        for item in range(1, n_items + 1):
            base_col = 2 + 5 * (item - 1)  # first item's dangerous-advice col is index 2
            item_key = key[item]
            for offset, qtype in enumerate(QUESTIONS):
                col = base_col + offset
                if col >= len(rater_row):
                    continue
                val = rater_row[col].strip()
                if not val:
                    continue
                if qtype == "comment":
                    comments[item].append(val)
                else:
                    mapped = unblind(val, item_key, qtype)
                    unblinded[qtype][item][mapped] += 1

    # ---- per-item tables ----
    print("=" * 100)
    print("PER-ITEM RESULTS  (full = fine-tuned+RAG+prompts pipeline, base = raw llama3.1)")
    print("=" * 100)
    for item in range(1, n_items + 1):
        k = key[item]
        print(f"\nItem {item}  (question_id={k['question_id']}, target_tier={k['target_tier']}, "
              f"A={k['response_A']}, B={k['response_B']})")
        for qtype in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]:
            counts = unblinded[qtype][item]
            parts = ", ".join(f"{label}: {n}" for label, n in counts.most_common())
            print(f"  {qtype:18s} {parts}")
        if comments[item]:
            print("  flagged comments:")
            for c in comments[item]:
                print(f"    - {c}")

    # ---- aggregate across all items ----
    print("\n" + "=" * 100)
    print("AGGREGATE ACROSS ALL ITEMS")
    print("=" * 100)
    agg = {q: Counter() for q in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]}
    for qtype, per_item in unblinded.items():
        for item, counts in per_item.items():
            agg[qtype].update(counts)

    for qtype, counts in agg.items():
        total = sum(counts.values())
        print(f"\n{qtype} (n={total} ratings across {n_items} items x {n_raters} raters)")
        for label, n in counts.most_common():
            print(f"  {label:28s} {n:3d}  ({100*n/total:.0f}%)")

    # dangerous-advice-attributed-to-full is the safety headline number
    danger_full = agg["dangerous_advice"].get("full", 0)
    danger_base = agg["dangerous_advice"].get("base", 0)
    print(f"\nSafety headline: full pipeline flagged as MORE dangerous in {danger_full} ratings, "
          f"base flagged as MORE dangerous in {danger_base} ratings "
          f"(out of {sum(agg['dangerous_advice'].values())} total).")

    # ---- breakdown by target tier ----
    print("\n" + "=" * 100)
    print("BREAKDOWN BY DISCLAIMER-POLICY TIER")
    print("=" * 100)
    items_by_tier = defaultdict(list)
    for item, k in key.items():
        items_by_tier[k["target_tier"]].append(item)

    for tier in sorted(items_by_tier):
        items = items_by_tier[tier]
        print(f"\nTier {tier}  (items {items})")
        for qtype in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]:
            counts = Counter()
            for item in items:
                counts.update(unblinded[qtype][item])
            total = sum(counts.values())
            parts = ", ".join(f"{label}: {n}" for label, n in counts.most_common())
            print(f"  {qtype:18s} {parts}")

    # ---- inter-rater agreement (Fleiss' kappa) ----
    print("\n" + "=" * 100)
    print("INTER-RATER AGREEMENT (Fleiss' kappa, on unblinded full/base/neutral labels)")
    print("=" * 100)
    kappas = {}
    for qtype in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]:
        categories = set()
        for counts in unblinded[qtype].values():
            categories.update(counts)
        item_answer_list = [unblinded[qtype][item] for item in range(1, n_items + 1)]
        kappa = fleiss_kappa(item_answer_list, categories)
        kappas[qtype] = kappa
        if kappa is None:
            print(f"  {qtype:18s} n/a (missing responses for some item)")
        else:
            print(f"  {qtype:18s} kappa = {kappa:.3f}")

    write_markdown(key, n_raters, n_items, unblinded, comments, agg, items_by_tier, kappas)
    print(f"\nWrote {os.path.relpath(REPORT, HERE)}")


def write_markdown(key, n_raters, n_items, unblinded, comments, agg, items_by_tier, kappas):
    lines = [
        "# Human eval results — pharmacist rater form",
        "",
        f"{n_raters} raters, {n_items} items. Full pipeline vs base llama3.1, unblinded via `form_key.csv`.",
        "",
        "## Per-item results",
        "",
    ]
    for item in range(1, n_items + 1):
        k = key[item]
        lines.append(f"### Item {item} (question_id={k['question_id']}, tier={k['target_tier']}, "
                      f"A={k['response_A']}, B={k['response_B']})")
        lines.append("")
        lines.append("| metric | counts |")
        lines.append("|---|---|")
        for qtype in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]:
            counts = unblinded[qtype][item]
            parts = ", ".join(f"{label}: {n}" for label, n in counts.most_common())
            lines.append(f"| {qtype} | {parts} |")
        if comments[item]:
            lines.append("")
            lines.append("Flagged comments:")
            for c in comments[item]:
                lines.append(f"- {c}")
        lines.append("")

    lines.append("## Aggregate across all items")
    lines.append("")
    lines.append("| metric | label | n | % |")
    lines.append("|---|---|---|---|")
    for qtype, counts in agg.items():
        total = sum(counts.values())
        for label, n in counts.most_common():
            lines.append(f"| {qtype} | {label} | {n} | {100*n/total:.0f}% |")
    lines.append("")

    danger_full = agg["dangerous_advice"].get("full", 0)
    danger_base = agg["dangerous_advice"].get("base", 0)
    lines.append(f"**Safety headline:** full pipeline flagged as MORE dangerous in "
                 f"{danger_full} ratings vs base in {danger_base} ratings "
                 f"(of {sum(agg['dangerous_advice'].values())} total).")
    lines.append("")

    lines.append("## Breakdown by disclaimer-policy tier")
    lines.append("")
    for tier in sorted(items_by_tier):
        items = items_by_tier[tier]
        lines.append(f"### Tier {tier} (items {items})")
        lines.append("")
        lines.append("| metric | counts |")
        lines.append("|---|---|")
        for qtype in ["dangerous_advice", "factual_accuracy", "referral", "overall_trust"]:
            counts = Counter()
            for item in items:
                counts.update(unblinded[qtype][item])
            parts = ", ".join(f"{label}: {n}" for label, n in counts.most_common())
            lines.append(f"| {qtype} | {parts} |")
        lines.append("")

    lines.append("## Inter-rater agreement (Fleiss' kappa)")
    lines.append("")
    lines.append("| metric | kappa |")
    lines.append("|---|---|")
    for qtype, kappa in kappas.items():
        lines.append(f"| {qtype} | {kappa:.3f} |" if kappa is not None else f"| {qtype} | n/a |")

    with open(REPORT, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
