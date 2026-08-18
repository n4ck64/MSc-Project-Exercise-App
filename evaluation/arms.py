"""
Ablation ladder configurations. One ArmConfig per rung, varied one step at a time.

Reconstructed from the `arm` field logged on every row of ladder.jsonl, which
records vars(arm) for the config that produced each answer.
"""
from dataclasses import dataclass

BASE = "llama3.1"
TUNED = "refit-dpo"
REVIEWER = "qwen2.5:7b"
BIOMISTRAL = "medical-expert:latest"


@dataclass
class ArmConfig:
    """One pipeline configuration. Every field is a single ablation variable."""
    answerer: str = BASE
    rewriter: str = BASE
    reviewer: str = REVIEWER
    nutrition_answerer: str = BIOMISTRAL
    rag: bool = True
    tools: bool = True
    sys_prompts: bool = True
    review: bool = True


# Exercise ladder. Rungs 1-4 add one component at a time to the base model;
# rungs 5 and 6 repeat rungs 1 and 4 with the fine-tuned model substituted.
EXERCISE_LADDER = {
    1: ("bare base model",
        ArmConfig(rag=False, sys_prompts=False, review=False)),
    2: ("+ reviewer and rewriter",
        ArmConfig(rag=False, sys_prompts=False)),
    3: ("+ RAG",
        ArmConfig(sys_prompts=False)),
    4: ("+ ReFit prompts",
        ArmConfig()),
    5: ("fine-tuned model alone",
        ArmConfig(answerer=TUNED, rewriter=TUNED,
                  rag=False, sys_prompts=False, review=False)),
    6: ("fine-tuned model + everything (shipped)",
        ArmConfig(answerer=TUNED, rewriter=TUNED)),
}

# Nutrition ladder. The answerer/rewriter are held at the fine-tuned model
# throughout; the variable is the nutrition specialist and what grounds it.
NUTRITION_LADDER = {
    1: ("bare base model",
        ArmConfig(answerer=TUNED, rewriter=TUNED, nutrition_answerer=BASE,
                  tools=False, sys_prompts=False, review=False)),
    2: ("BioMistral swapped in",
        ArmConfig(answerer=TUNED, rewriter=TUNED,
                  tools=False, sys_prompts=False, review=False)),
    3: ("+ PHE tool grounding",
        ArmConfig(answerer=TUNED, rewriter=TUNED,
                  sys_prompts=False, review=False)),
    4: ("+ reviewer and rewriter",
        ArmConfig(answerer=TUNED, rewriter=TUNED, sys_prompts=False)),
    5: ("+ ReFit prompts (shipped)",
        ArmConfig(answerer=TUNED, rewriter=TUNED)),
}

# The persona sweep compares the two ends of the exercise ladder only.
PERSONA_ARMS = {
    1: EXERCISE_LADDER[1],
    6: EXERCISE_LADDER[6],
}

# Which rung each rung is the one-step successor of. The exercise ladder
# branches: rung 5 is rung 1 fine-tuned, rung 6 is rung 4 fine-tuned.
EXERCISE_PREDECESSOR = {2: 1, 3: 2, 4: 3, 5: 1, 6: 4}
NUTRITION_PREDECESSOR = {2: 1, 3: 2, 4: 3, 5: 4}

# Swapping the fine-tuned model in changes answerer and rewriter together;
# they are the same model in two roles, so it counts as one intervention.
PAIRED_FIELDS = frozenset({"answerer", "rewriter"})


def verify_ladder(ladder, name, predecessor):
    """Asserts each rung differs from its predecessor by exactly one variable,
    so the one-variable-per-rung claim holds by construction rather than by care."""
    for rung, previous in sorted(predecessor.items()):
        current_config = vars(ladder[rung][1])
        previous_config = vars(ladder[previous][1])
        changed = {field for field in current_config
                   if current_config[field] != previous_config[field]}

        if changed == PAIRED_FIELDS:
            continue
        if len(changed) != 1:
            raise AssertionError(
                f"{name} ladder: rung {previous} -> {rung} changes "
                f"{sorted(changed) or 'nothing'}, expected one variable")
