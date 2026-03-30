"""Download datasets and prepare tasks for Experiment 011.

Downloads from HuggingFace, grades difficulty, outputs JSONL files.

Usage:
    python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset gsm8k
    python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset sst5
    python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset goemo
    python -m experiments.011_guided_decoding_v2.prepare_tasks --dataset banking77
    python -m experiments.011_guided_decoding_v2.prepare_tasks --all
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import random
import re
import sys
from pathlib import Path
from typing import Any

import boto3

from .schemas import LABELS

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

EXPERIMENT_DIR = Path(__file__).parent
TASKS_DIR = EXPERIMENT_DIR / "tasks"

SEED = 42
GRADING_MODEL = "us.anthropic.claude-haiku-4-5-20251001-v1:0"
GRADING_POOL_SIZE = 300

# Confidence thresholds for difficulty grading
EASY_THRESHOLD = 0.8
MEDIUM_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# GSM8K: mechanical difficulty grading by step count
# ---------------------------------------------------------------------------

def _count_gsm8k_steps(answer_text: str) -> int:
    """Count arithmetic operations in GSM8K solution (<<...>> annotations)."""
    return len(re.findall(r"<<.*?>>", answer_text))


def _extract_gsm8k_answer(answer_text: str) -> int:
    """Extract the final numeric answer after ####."""
    match = re.search(r"####\s*(-?[\d,]+)", answer_text)
    if match:
        return int(match.group(1).replace(",", ""))
    raise ValueError(f"Cannot extract answer from: {answer_text[:100]}")


def prepare_gsm8k() -> None:
    """Load GSM8K test set, grade by step count, output balanced JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "gsm8k.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 100:
            logger.info("gsm8k.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading GSM8K test split...")
    ds = load_dataset("openai/gsm8k", "main", split="test")
    logger.info("Loaded %d problems", len(ds))

    # Grade by step count
    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for item in ds:
        steps = _count_gsm8k_steps(item["answer"])
        try:
            answer = _extract_gsm8k_answer(item["answer"])
        except ValueError:
            continue

        if steps <= 2:
            difficulty = "easy"
        elif steps <= 4:
            difficulty = "medium"
        else:
            difficulty = "hard"

        buckets[difficulty].append({
            "question": item["question"],
            "answer": answer,
            "steps": steps,
            "solution": item["answer"],
        })

    for d, items in buckets.items():
        logger.info("  %s: %d problems available", d, len(items))

    # Balanced sampling
    rng = random.Random(SEED)
    targets = {"easy": 35, "medium": 35, "hard": 30}
    selected = []
    for difficulty, target in targets.items():
        pool = buckets[difficulty]
        rng.shuffle(pool)
        chosen = pool[:target]
        selected.extend(
            {
                "id": f"gsm8k_{i:03d}",
                "dataset": "gsm8k",
                "prompt": item["question"],
                "expected_answer": item["answer"],
                "difficulty": difficulty,
                "metadata": {"steps": item["steps"]},
            }
            for i, item in enumerate(chosen, start=len(selected))
        )

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d GSM8K tasks to %s", len(selected), out_path)


# ---------------------------------------------------------------------------
# Classification datasets: Claude confidence grading
# ---------------------------------------------------------------------------

GRADES_CACHE_DIR = EXPERIMENT_DIR / "tasks" / ".grade_cache"


def _grade_with_claude(
    texts: list[str],
    labels: list[str],
    task_description: str,
    cache_key: str = "",
) -> list[tuple[str, float]]:
    """Grade difficulty of classification samples using Claude Haiku.

    Returns list of (predicted_label, confidence) tuples.
    Caches results to avoid re-grading on re-runs.
    """
    # Check cache
    if cache_key:
        GRADES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = GRADES_CACHE_DIR / f"{cache_key}.json"
        if cache_path.exists():
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            if len(cached) == len(texts):
                logger.info("  Using cached grades from %s", cache_path.name)
                return [(r["label"], r["confidence"]) for r in cached]

    client = boto3.client("bedrock-runtime", region_name="us-east-1")
    results = []
    labels_str = ", ".join(labels)

    for i, text in enumerate(texts):
        prompt = (
            f"Task: {task_description}\n"
            f"Categories: {labels_str}\n\n"
            f"Text: \"{text}\"\n\n"
            f"Classify this text into exactly one category. "
            f"Respond in this exact format:\n"
            f"label: <category>\n"
            f"confidence: <0.0 to 1.0>\n\n"
            f"Where confidence reflects how clear/unambiguous the classification is."
        )

        try:
            response = client.converse(
                modelId=GRADING_MODEL,
                messages=[{"role": "user", "content": [{"text": prompt}]}],
                inferenceConfig={"maxTokens": 64, "temperature": 0.0},
            )
            content = response["output"]["message"]["content"][0]["text"]

            # Parse label and confidence
            label_match = re.search(r"label:\s*(.+)", content, re.IGNORECASE)
            conf_match = re.search(r"confidence:\s*([\d.]+)", content, re.IGNORECASE)

            label = label_match.group(1).strip() if label_match else ""
            confidence = float(conf_match.group(1)) if conf_match else 0.5

            results.append((label, confidence))
        except Exception as e:
            logger.warning("Grading failed for sample %d: %s", i, e)
            results.append(("", 0.5))

        if (i + 1) % 50 == 0:
            logger.info("  Graded %d/%d samples", i + 1, len(texts))

    # Save cache
    if cache_key:
        GRADES_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        cache_path = GRADES_CACHE_DIR / f"{cache_key}.json"
        cache_data = [{"label": l, "confidence": c} for l, c in results]
        cache_path.write_text(json.dumps(cache_data, ensure_ascii=False), encoding="utf-8")
        logger.info("  Saved grades cache: %s", cache_path.name)

    return results


def _assign_difficulty_absolute(confidence: float) -> str:
    """Absolute thresholds — may produce empty buckets for easy tasks."""
    if confidence > EASY_THRESHOLD:
        return "easy"
    elif confidence > MEDIUM_THRESHOLD:
        return "medium"
    else:
        return "hard"


def _assign_difficulty_relative(
    confidences: list[float],
) -> list[str]:
    """Percentile-based: bottom 25% = hard, middle 37.5% = medium, top 37.5% = easy.

    Ensures all three buckets are populated regardless of absolute confidence range.
    """
    sorted_confs = sorted(confidences)
    n = len(sorted_confs)
    p25 = sorted_confs[n // 4] if n >= 4 else sorted_confs[0]
    p625 = sorted_confs[int(n * 0.625)] if n >= 2 else sorted_confs[-1]

    result = []
    for c in confidences:
        if c <= p25:
            result.append("hard")
        elif c <= p625:
            result.append("medium")
        else:
            result.append("easy")
    return result


def prepare_sst5() -> None:
    """Load SST-5, grade difficulty with Claude, output JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "sst5.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 80:
            logger.info("sst5.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading SST-5 test split...")
    ds = load_dataset("SetFit/sst5", split="test")
    logger.info("Loaded %d samples", len(ds))

    label_map = {0: "very_negative", 1: "negative", 2: "neutral", 3: "positive", 4: "very_positive"}
    labels = LABELS["sst5"]

    # Sample candidate pool
    rng = random.Random(SEED)
    indices = list(range(len(ds)))
    rng.shuffle(indices)
    pool_indices = indices[:GRADING_POOL_SIZE]

    texts = [ds[i]["text"] for i in pool_indices]
    ground_truths = [label_map[ds[i]["label"]] for i in pool_indices]

    logger.info("Grading %d candidates with Claude...", len(texts))
    grades = _grade_with_claude(texts, labels, "sentiment classification (5-level)", cache_key="sst5")

    # Bucket by difficulty (relative percentiles — ensures all 3 buckets populated)
    confidences = [conf for _, conf in grades]
    difficulties = _assign_difficulty_relative(confidences)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for idx, (text, gt, (_, conf), diff) in enumerate(
        zip(texts, ground_truths, grades, difficulties)
    ):
        buckets[diff].append({
            "text": text,
            "label": gt,
            "confidence": conf,
            "pool_idx": idx,
        })

    for d, items in buckets.items():
        logger.info("  %s: %d samples", d, len(items))

    # Balanced sampling
    targets = {"easy": 30, "medium": 30, "hard": 20}
    selected = _balanced_select(buckets, targets, "sst5", rng)

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d SST-5 tasks to %s", len(selected), out_path)


def prepare_goemo() -> None:
    """Load GoEmotions (single-label only), grade difficulty, output JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "goemo.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 80:
            logger.info("goemo.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading GoEmotions test split...")
    ds = load_dataset("google-research-datasets/go_emotions", "simplified", split="test")
    logger.info("Loaded %d samples", len(ds))

    labels = LABELS["goemo"]

    # Filter single-label samples only
    single_label_samples = []
    for item in ds:
        item_labels = item["labels"]
        if len(item_labels) == 1:
            single_label_samples.append({
                "text": item["text"],
                "label": labels[item_labels[0]],
            })
    logger.info("Single-label samples: %d / %d", len(single_label_samples), len(ds))

    # Sample candidate pool
    rng = random.Random(SEED)
    rng.shuffle(single_label_samples)
    pool = single_label_samples[:GRADING_POOL_SIZE]

    texts = [s["text"] for s in pool]
    ground_truths = [s["label"] for s in pool]

    logger.info("Grading %d candidates with Claude...", len(texts))
    grades = _grade_with_claude(texts, labels, "emotion detection (28 emotions)", cache_key="goemo")

    # Bucket by difficulty (relative percentiles)
    confidences = [conf for _, conf in grades]
    difficulties = _assign_difficulty_relative(confidences)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for sample, (_, conf), diff in zip(pool, grades, difficulties):
        buckets[diff].append({
            "text": sample["text"],
            "label": sample["label"],
            "confidence": conf,
        })

    for d, items in buckets.items():
        logger.info("  %s: %d samples", d, len(items))

    targets = {"easy": 30, "medium": 30, "hard": 20}
    selected = _balanced_select(buckets, targets, "goemo", rng)

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d GoEmotions tasks to %s", len(selected), out_path)


def prepare_banking77() -> None:
    """Load BANKING77, grade difficulty with Claude, output JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "banking77.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 140:
            logger.info("banking77.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading BANKING77 test split...")
    ds = load_dataset("legacy-datasets/banking77", split="test")
    logger.info("Loaded %d samples", len(ds))

    # Use dataset's own label names (authoritative)
    ds_labels = ds.features["label"].names
    logger.info("  %d label classes from dataset", len(ds_labels))

    # Sample candidate pool
    rng = random.Random(SEED)
    all_samples = [{"text": item["text"], "label": ds_labels[item["label"]]} for item in ds]
    rng.shuffle(all_samples)
    pool = all_samples[:GRADING_POOL_SIZE]

    texts = [s["text"] for s in pool]

    logger.info("Grading %d candidates with Claude...", len(texts))
    grades = _grade_with_claude(
        texts, ds_labels, "banking customer intent classification (77 intents)",
        cache_key="banking77",
    )

    # Bucket by difficulty (relative percentiles)
    confidences = [conf for _, conf in grades]
    difficulties = _assign_difficulty_relative(confidences)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for sample, (_, conf), diff in zip(pool, grades, difficulties):
        buckets[diff].append({
            "text": sample["text"],
            "label": sample["label"],
            "confidence": conf,
        })

    for d, items in buckets.items():
        logger.info("  %s: %d samples", d, len(items))

    targets = {"easy": 50, "medium": 50, "hard": 40}
    selected = _balanced_select(buckets, targets, "banking77", rng)

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d BANKING77 tasks to %s", len(selected), out_path)


# ---------------------------------------------------------------------------
# Few-NERD NER: mechanical difficulty grading by entity count
# ---------------------------------------------------------------------------

def _flat_tags_to_entities(
    tokens: list[str], ner_tags: list[int], tag_names: list[str],
) -> list[dict]:
    """Convert flat (non-IOB) token-level tags to entity spans.

    Consecutive tokens with the same non-O tag form one entity.
    """
    entities = []
    current_tokens: list[str] = []
    current_type: str | None = None

    for token, tag_id in zip(tokens, ner_tags):
        tag = tag_names[tag_id]
        if tag == "O":
            if current_tokens:
                entities.append({"text": " ".join(current_tokens), "type": current_type})
                current_tokens = []
                current_type = None
        elif tag == current_type:
            current_tokens.append(token)
        else:
            if current_tokens:
                entities.append({"text": " ".join(current_tokens), "type": current_type})
            current_tokens = [token]
            current_type = tag

    if current_tokens:
        entities.append({"text": " ".join(current_tokens), "type": current_type})

    return entities


def prepare_fewnerd() -> None:
    """Load Few-NERD NER test set, grade by entity count, output JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "fewnerd.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 100:
            logger.info("fewnerd.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading Few-NERD supervised test split...")
    ds = load_dataset("DFKI-SLT/few-nerd", "supervised", split="test")
    logger.info("Loaded %d sentences", len(ds))

    tag_names = ds.features["ner_tags"].feature.names
    logger.info("  NER tags: %s", tag_names)

    # Convert all samples and grade by entity count
    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for item in ds:
        tokens = item["tokens"]
        ner_tags = item["ner_tags"]
        entities = _flat_tags_to_entities(tokens, ner_tags, tag_names)

        if not entities:
            continue

        n_entities = len(entities)
        if n_entities <= 2:
            difficulty = "easy"
        elif n_entities <= 4:
            difficulty = "medium"
        else:
            difficulty = "hard"

        sentence = " ".join(tokens)
        buckets[difficulty].append({
            "text": sentence,
            "entities": entities,
            "n_entities": n_entities,
        })

    for d, items in buckets.items():
        logger.info("  %s: %d sentences available", d, len(items))

    # Balanced sampling
    rng = random.Random(SEED)
    targets = {"easy": 35, "medium": 35, "hard": 30}
    selected = []
    task_idx = 0
    for difficulty, target in targets.items():
        pool = buckets[difficulty]
        rng.shuffle(pool)
        if len(pool) < target:
            logger.warning(
                "fewnerd %s: only %d samples (need %d), taking all",
                difficulty, len(pool), target,
            )
        chosen = pool[:target]
        for item in chosen:
            selected.append({
                "id": f"fewnerd_{task_idx:03d}",
                "dataset": "fewnerd",
                "prompt": item["text"],
                "expected_answer": item["entities"],
                "difficulty": difficulty,
                "metadata": {"n_entities": item["n_entities"]},
            })
            task_idx += 1

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d Few-NERD tasks to %s", len(selected), out_path)


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------

def _balanced_select(
    buckets: dict[str, list[dict]],
    targets: dict[str, int],
    dataset_name: str,
    rng: random.Random,
) -> list[dict]:
    """Select balanced tasks from difficulty buckets, output as JSONL records."""
    selected = []
    task_idx = 0
    for difficulty, target in targets.items():
        pool = buckets[difficulty]
        rng.shuffle(pool)
        # If not enough samples, take all available and warn
        if len(pool) < target:
            logger.warning(
                "%s %s: only %d samples (need %d), taking all",
                dataset_name, difficulty, len(pool), target,
            )
        chosen = pool[:target]
        for item in chosen:
            selected.append({
                "id": f"{dataset_name}_{task_idx:03d}",
                "dataset": dataset_name,
                "prompt": item["text"],
                "expected_answer": item["label"],
                "difficulty": difficulty,
                "metadata": {"claude_confidence": item["confidence"]},
            })
            task_idx += 1
    return selected


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def prepare_recipe() -> None:
    """Load recipe dataset, grade by ingredient count, output JSONL."""
    from datasets import load_dataset

    out_path = TASKS_DIR / "recipe.jsonl"
    if out_path.exists():
        count = sum(1 for _ in open(out_path))
        if count >= 100:
            logger.info("recipe.jsonl already exists (%d tasks), skipping", count)
            return

    logger.info("Loading recipes-with-nutrition...")
    ds = load_dataset("datahiveai/recipes-with-nutrition", split="train")
    logger.info("Loaded %d recipes", len(ds))

    rng = random.Random(SEED)
    indices = list(range(len(ds)))
    rng.shuffle(indices)

    buckets: dict[str, list[dict]] = {"easy": [], "medium": [], "hard": []}
    for idx in indices[:2000]:  # Sample pool
        item = ds[idx]
        ingredient_lines = json.loads(item["ingredient_lines"])
        ingredients_raw = json.loads(item["ingredients"])
        cuisine_raw = json.loads(item["cuisine_type"])
        diet_raw = json.loads(item["diet_labels"])

        n_ingredients = len(ingredients_raw)
        if n_ingredients < 3:
            continue  # Too simple

        if n_ingredients <= 6:
            difficulty = "easy"
        elif n_ingredients <= 10:
            difficulty = "medium"
        else:
            difficulty = "hard"

        # Build input text (recipe_name + servings + ingredient lines)
        input_lines = [
            f"Recipe: {item['recipe_name']}",
            f"Servings: {int(item['servings'])}",
            "",
            "Ingredients:",
        ]
        for line in ingredient_lines:
            input_lines.append(f"- {line}")
        input_text = "\n".join(input_lines)

        # Build expected answer
        expected_ingredients = []
        for ing in ingredients_raw:
            expected_ingredients.append({
                "food": ing["food"],
                "quantity": ing["quantity"],
                "unit": ing["measure"],
            })

        expected = {
            "recipe_name": item["recipe_name"],
            "servings": int(item["servings"]),
            "ingredients": expected_ingredients,
            "cuisine_type": cuisine_raw[0] if cuisine_raw else "unknown",
            "diet_labels": diet_raw,
        }

        buckets[difficulty].append({
            "text": input_text,
            "expected": expected,
            "n_ingredients": n_ingredients,
        })

    for d, items in buckets.items():
        logger.info("  %s: %d recipes available", d, len(items))

    targets = {"easy": 35, "medium": 35, "hard": 30}
    selected = []
    task_idx = 0
    for difficulty, target in targets.items():
        pool = buckets[difficulty]
        rng.shuffle(pool)
        if len(pool) < target:
            logger.warning("recipe %s: only %d (need %d)", difficulty, len(pool), target)
        chosen = pool[:target]
        for item in chosen:
            selected.append({
                "id": f"recipe_{task_idx:03d}",
                "dataset": "recipe",
                "prompt": item["text"],
                "expected_answer": item["expected"],
                "difficulty": difficulty,
                "metadata": {"n_ingredients": item["n_ingredients"]},
            })
            task_idx += 1

    TASKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        for task in selected:
            f.write(json.dumps(task, ensure_ascii=False) + "\n")
    logger.info("Wrote %d recipe tasks to %s", len(selected), out_path)


PREPARERS = {
    "gsm8k": prepare_gsm8k,
    "sst5": prepare_sst5,
    "goemo": prepare_goemo,
    "banking77": prepare_banking77,
    "fewnerd": prepare_fewnerd,
    "recipe": prepare_recipe,
}


def main():
    parser = argparse.ArgumentParser(description="Prepare tasks for Exp 011")
    parser.add_argument(
        "--dataset",
        choices=list(PREPARERS.keys()),
        help="Dataset to prepare (or use --all)",
    )
    parser.add_argument("--all", action="store_true", help="Prepare all datasets")
    args = parser.parse_args()

    if not args.dataset and not args.all:
        parser.error("Specify --dataset <name> or --all")

    datasets = list(PREPARERS.keys()) if args.all else [args.dataset]

    for name in datasets:
        logger.info("=== Preparing %s ===", name)
        PREPARERS[name]()


if __name__ == "__main__":
    main()
