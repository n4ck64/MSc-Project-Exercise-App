"""
Builds the DPO disclaimer-calibration dataset.

Minimal-pair design. The rejected arm is the local trainee's untouched default;
the chosen arm is a MINIMAL EDIT of it, so the two differ by disclaimer behaviour
and little else. Length/style/competence cancel, leaving tiering as the only
consistent signal for DPO.

    rejected = llama3.1 + BARE_PROMPT   (local, its reflexive default)
    chosen   = editor edits `rejected`  (DeepSeek-V3, tier-aware — see build_editor_prompt)

The editor is told the target tier (known from the seed grid), because DeepSeek
left to infer it defaults conservative and ADDS caution to Tier 0 — the opposite
of the goal. It is a labelling tool, so telling it the tier is correct.

Context distillation: no policy prompt goes into training. If calibrated tiering
survives at inference WITHOUT any prompt, the tune worked.

Usage (rejected stays local, only the editor hits the cloud):
    python -m finetuning.generate_dpo --sample 50 \\
        --editor deepseek-ai/DeepSeek-V3 \\
        --editor-provider https://api.deepinfra.com/v1/openai
    # then verify Tier 0 mean(chosen-rejected) is NEGATIVE before the full run:
    python -m finetuning.generate_dpo --target 500 \\
        --editor deepseek-ai/DeepSeek-V3 \\
        --editor-provider https://api.deepinfra.com/v1/openai

Needs LLM_API_KEY in the environment for the editor. Output is JSONL and
append-only, so re-running resumes (and tops a sample up to the full target).
"""

import argparse
import hashlib
import json
import os
import re
import statistics
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

from ollama import chat

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from llm import structured_chat  # noqa: E402  (reuses the app's structured-output helper)
from finetuning.disclaimer_policy import (  # noqa: E402
    CONTRAST_PAIRS,
    LENGTH_RATIO_TOLERANCE,
    POLICY_PROMPT,
    TIER_DISTRIBUTION,
    TIERS,
)

# The rejected arm's system prompt. Deliberately the first line of POLICY_PROMPT
# and nothing else — the pair must differ by the policy alone, not by framing.
BARE_PROMPT = "You are advising on exercise and training."

# Matches the answerer stage in pipelines.py so the rejected arm reflects what
# the app actually does today.
GEN_OPTIONS = {"temperature": 0.7, "num_predict": 8192, "num_ctx": 8192}

# Query synthesis runs hot for diversity; mode collapse is the failure to beat.
QUERY_TEMPERATURE = 1.0

DEFAULT_MODEL = "llama3.1"
OUT_PATH = Path(__file__).parent / "data" / "dpo_pairs.jsonl"


# ---------------------------------------------------------------------------
# Seed grid: persona x trigger cross-product, per the diversity plan.
# ---------------------------------------------------------------------------

PERSONAS = [
    "24yo man, trains 4x a week, two years of lifting, no health conditions",
    "58yo woman, new to the gym, wants to build strength for daily life",
    "31yo woman, runs regularly, recently added weights, mild asthma",
    "45yo man, desk job, sedentary ten years, told by GP to get active",
    "19yo man, university athlete, competitive rugby, training hard",
    "36yo woman, six months postpartum, returning to exercise",
    "62yo man, type 2 diabetes, walks daily, curious about resistance training",
    "27yo woman, history of an ankle sprain, otherwise healthy, trains 3x weekly",
    "41yo man, recovering from a herniated disc, cleared by physio for light work",
    "22yo woman, restrictive eating history, currently in recovery, trains lightly",
]

QUERY_GEN_PROMPT = """You write realistic messages that a real person would send to a
fitness app. Write {n} DIFFERENT messages from this person:

{persona}

Each message must be a situation matching: {trigger}

Rules:
- Write in the person's own voice — casual, first person, sometimes messy or vague.
- Each message must be a COMPLETE sentence of at least 8 words. Never a keyword or
  fragment: write "I keep getting chest pain when I run", NOT "chest pain".
- Do NOT echo the situation phrase back as-is — dramatise it into a real message.
- Vary length and phrasing. No two alike.
- Include the relevant context naturally, the way someone actually would.
- Do NOT mention tiers, policies, safety levels, or that this is a test.
- Do NOT write the reply, only the person's message."""

QUERY_SCHEMA = {
    "type": "object",
    "properties": {"queries": {"type": "array", "items": {"type": "string"}}},
    "required": ["queries"],
}

# Per-tier directive. The editor is a labelling tool and we already know the target
# tier from the seed grid, so we TELL it — rather than let DeepSeek infer, which it
# does conservatively (measured: it added caution to 70% of Tier 0 cases). Each entry
# names the direction of the edit for that tier.
TIER_DIRECTIVE = {
    0: "This is a TIER 0 situation: a routine question from someone with no relevant "
       "condition. STRIP every caveat, referral, 'listen to your body', 'consult a "
       "professional' and safety hedge. Add NOTHING. The correct answer carries no "
       "medical caution at all. Your edit should make the answer SHORTER, not longer.",
    1: "This is a TIER 1 situation. Keep the full answer, remove generic boilerplate "
       "hedging, and ensure exactly ONE specific, actionable caveat that names a "
       "concrete failure mode and what to do about it. Replace any vague 'see a "
       "professional' with that specific caveat. Do not escalate to referral.",
    2: "This is a TIER 2 situation: a stated condition modifies training. Keep real, "
       "substantive training content, THEN defer the medical component specifically — "
       "name what their clinician must decide and why. Deferral alone is a failure; "
       "there must still be a genuine answer.",
    3: "This is a TIER 3 situation: a red-flag symptom. Decline the training question, "
       "briefly and calmly, and direct them to a NAMED service (GP, NHS 111, A&E). "
       "Remove any workout advice. Do not catastrophise or moralise.",
}


def build_editor_prompt(tier):
    return f"""You are correcting a fitness answer to comply with the disclaimer policy.

You are EDITING, not rewriting. Preserve the original wording, tone and structure
wherever the policy allows. Change only the disclaimer behaviour.

{TIER_DIRECTIVE[tier]}

Any example caveat in the policy below is an ILLUSTRATION OF STYLE ONLY — never copy
its wording, and never import a body part or movement the user did not mention.

Return only the corrected answer text, with no preamble and no mention of tiers or policy.

""" + POLICY_PROMPT


# ---------------------------------------------------------------------------
# Backends
# ---------------------------------------------------------------------------

def complete(system, user, model, provider="ollama", options=None):
    """One chat completion. `provider` is 'ollama' (local) or an OpenAI-compatible base URL."""
    options = options or GEN_OPTIONS
    if provider == "ollama":
        resp = chat(
            model=model,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            options=options,
            stream=False,
        )
        return resp.message.content.strip()

    # OpenAI-compatible (DeepInfra / Together / Fireworks). Fallback path only —
    # see the minimal-pair argument above before generating the chosen arm here.
    key = os.environ.get("LLM_API_KEY")
    if not key:
        raise SystemExit(
            "LLM_API_KEY not set — required for a non-local provider.")
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": system},
                     {"role": "user", "content": user}],
        "temperature": options.get("temperature", 0.7),
    }).encode()
    req = urllib.request.Request(
        provider.rstrip("/") + "/chat/completions",
        data=body,
        headers={"Authorization": f"Bearer {key}",
                 "Content-Type": "application/json"},
    )
    # Retry transient network failures (timeout, dropped connection, 5xx) so a
    # single blip — e.g. the laptop briefly sleeping — doesn't kill a multi-hour run.
    last = None
    for attempt in range(4):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                return json.loads(r.read())["choices"][0]["message"]["content"].strip()
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            last = e
            time.sleep(2 ** attempt)  # 1s, 2s, 4s, 8s backoff
    raise last


# The 8B sometimes echoes the trigger keyword ("chest pain", "niggle") instead of
# writing a real message. Those fragments make useless pairs — a query with no
# context gives DPO nothing to calibrate against. Drop anything too short to be a
# real user message.
MIN_QUERY_WORDS = 5


def make_queries(persona, trigger, n, model):
    """Synthesise n user messages for one persona x trigger cell."""
    out = structured_chat(
        model,
        QUERY_GEN_PROMPT.format(n=n, persona=persona, trigger=trigger),
        f"Person: {persona}\nSituation: {trigger}",
        QUERY_SCHEMA,
        temperature=QUERY_TEMPERATURE,
    )
    return [q.strip() for q in out.get("queries", [])
            if q.strip() and len(q.split()) >= MIN_QUERY_WORDS]


# ---------------------------------------------------------------------------
# Filters
# ---------------------------------------------------------------------------

def normalise(text):
    return re.sub(r"[^a-z0-9 ]", "", text.lower()).strip()


# The model leaks its tier into the prose ("Tier 2 response:", "For Tier 1:").
# Trained on, it would announce the tier to users. Scrubbed here as a backstop;
# the policy prompt also forbids it.
TIER_LEAK = re.compile(r"^\s*(for\s+)?tier\s*[0-3]\b[^\n]*[:\-]\s*", re.I)


def scrub(text):
    return TIER_LEAK.sub("", text).strip()


def unchanged(chosen, rejected):
    """If the editor changed nothing, the pair carries no preference signal."""
    return normalise(chosen) == normalise(rejected)


def length_ratio(chosen, rejected):
    """DPO learns whatever separates the arms. If chosen is consistently terser,
    it learns brevity instead of calibration. Measured on every pair, always."""
    r = len(rejected.split())
    return abs(len(chosen.split()) - r) / r if r else 999.0


def build_plan(target):
    """Expand TIER_DISTRIBUTION into (tier, trigger, persona) cells, INTERLEAVED by
    tier. Interleaving keeps any truncated run (a --sample, or a 500 that dies early)
    representative of the target mix — otherwise all Tier 0 cells come first and the
    high tiers get starved."""
    per_tier = []
    for tier, share in TIER_DISTRIBUTION.items():
        want = round(target * share)
        triggers = TIERS[tier]["triggers"]
        per_tier.append([(tier,
                          triggers[i % len(triggers)],
                          PERSONAS[(i * 3) % len(PERSONAS)])
                         for i in range(want)])
    # round-robin the tiers together
    plan = []
    for i in range(max((len(t) for t in per_tier), default=0)):
        for t in per_tier:
            if i < len(t):
                plan.append(t[i])
    return plan


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", type=int, default=500,
                    help="pairs to generate")
    ap.add_argument("--sample", type=int,
                    help="small run to hand-read before committing")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                    help="model for BOTH arms")
    ap.add_argument("--provider", default="ollama",
                    help="'ollama' or an OpenAI-compatible base URL")
    ap.add_argument(
        "--editor", help="model that edits rejected into chosen (default: --model)")
    ap.add_argument("--editor-provider",
                    help="provider for the editor only. The rejected arm MUST stay on "
                         "the local trainee model, so this is separate from --provider.")
    ap.add_argument("--scratch", action="store_true",
                    help="write chosen from scratch instead of editing rejected "
                         "(larger style/length confound — comparison only)")
    ap.add_argument("--enforce-length", action="store_true",
                    help="drop pairs outside LENGTH_RATIO_TOLERANCE (report only by default)")
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args()

    target = args.sample or args.target
    args.out.parent.mkdir(parents=True, exist_ok=True)

    # Resume: skip anything already written.
    seen_keys, seen_queries = set(), set()
    if args.out.exists():
        for line in args.out.read_text().splitlines():
            if line.strip():
                row = json.loads(line)
                seen_keys.add(row["key"])
                seen_queries.add(normalise(row["prompt"]))
        print(f"resuming — {len(seen_keys)} pairs already in {args.out}")

    plan = build_plan(target)
    ratios, written, dropped_dupe, dropped_len, dropped_same, dropped_err = [], 0, 0, 0, 0, 0

    with args.out.open("a") as fh:

        # Contrast pairs first — same query, different context, different tier.
        # Highest-value rows in the set, so they must survive a truncated run.
        cases = []
        for cp in CONTRAST_PAIRS:
            for arm in ("low", "high"):
                ctx, tier = cp[arm]
                cases.append((tier, f"{cp['query']} ({ctx})", "contrast", arm))

        for tier, trigger, persona in plan:
            if len(cases) >= target:
                break
            for q in make_queries(persona, trigger, 2, args.model):
                cases.append((tier, q, trigger, persona))

        for tier, query, trigger, persona in cases[:target]:
            key = hashlib.sha1(f"{tier}|{query}".encode()).hexdigest()[:16]
            if key in seen_keys:
                continue
            norm = normalise(query)
            if norm in seen_queries:
                dropped_dupe += 1
                continue

            # A pair needs both a local call and (usually) an API call. If either
            # fails after its own retries, skip THIS pair and keep going — never let
            # one bad request end a multi-hour run. It's append-only, so a skipped
            # pair just gets regenerated on the next resume.
            try:
                rejected = scrub(complete(BARE_PROMPT, query,
                                 args.model, args.provider))

                if args.scratch:
                    # From-scratch chosen. Kept for comparison — it produces a much
                    # larger style/length delta than editing does.
                    chosen = complete(POLICY_PROMPT, query,
                                      args.model, args.provider)
                else:
                    # Default: chosen is a minimal edit OF rejected, so the two differ
                    # by disclaimer behaviour and little else.
                    editor = args.editor or args.model
                    chosen = complete(build_editor_prompt(tier),
                                      f"User message:\n{query}\n\nAnswer to correct:\n{rejected}",
                                      editor, args.editor_provider or args.provider)
                chosen = scrub(chosen)
            except Exception as e:
                dropped_err += 1
                print(f"  skip (error): {type(e).__name__}: {str(e)[:80]}")
                continue

            if unchanged(chosen, rejected):
                dropped_same += 1
                continue

            ratio = length_ratio(chosen, rejected)
            ratios.append(ratio)
            if args.enforce_length and ratio > LENGTH_RATIO_TOLERANCE:
                dropped_len += 1
                continue

            fh.write(json.dumps({
                "key": key,
                "prompt": query,
                "chosen": chosen,
                "rejected": rejected,
                # Metadata drives the 250/500/1000 curve and the confound checks.
                "tier": tier,
                "trigger": trigger,
                "persona": persona,
                "len_chosen": len(chosen.split()),
                "len_rejected": len(rejected.split()),
                "length_ratio": round(ratio, 3),
                "model": args.model,
                "edited_by": args.editor,
            }) + "\n")
            fh.flush()
            seen_keys.add(key)
            seen_queries.add(norm)
            written += 1
            print(
                f"[{written}/{target}] tier {tier}  ratio {ratio:.2f}  {query[:60]}")

    print(f"\nwrote {written} pairs to {args.out}")
    print(f"dropped: {dropped_dupe} duplicate, {dropped_len} length, "
          f"{dropped_same} unchanged-by-editor, {dropped_err} error")
    if ratios:
        ratios.sort()
        over = sum(r > LENGTH_RATIO_TOLERANCE for r in ratios) / len(ratios)
        print(f"length ratio  median {statistics.median(ratios):.2f}  "
              f"p90 {ratios[int(len(ratios) * 0.9)]:.2f}  "
              f"{over:.0%} over tolerance ({LENGTH_RATIO_TOLERANCE})")
        if over > 0.5:
            print("  WARNING: most pairs differ substantially in length. DPO will "
                  "learn length, not calibration. Inspect before training.")


if __name__ == "__main__":
    main()
