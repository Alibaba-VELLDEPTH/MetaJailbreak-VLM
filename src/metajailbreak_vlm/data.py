"""Task validation and deterministic category-stratified splitting."""

import json
import os
import random
from pathlib import Path
from .prompts import seed_candidate


def load_dataset_from_directory(directory_path, source_type):
    directory = Path(directory_path)
    if not directory.is_dir():
        raise FileNotFoundError(f"Task directory not found: {directory}")
    tasks = []
    for path in sorted(directory.glob("*.json")):
        try:
            records = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError) as error:
            raise ValueError(f"Cannot read {path}: {error}") from error
        if not isinstance(records, dict):
            raise ValueError(f"Expected a JSON object: {path}")
        category = path.stem.replace("_processed", "")
        for record_id, content in records.items():
            if not isinstance(content, dict):
                raise ValueError(f"{path}, record {record_id}: expected object")
            instruction = (
                content.get("changed_question")
                or content.get("Changed Question")
                or content.get("Question")
            )
            if not isinstance(instruction, str) or not instruction.strip():
                raise ValueError(f"{path}, record {record_id}: missing question string")
            task_id = f"{category}_{record_id}"
            if "/" in task_id or "\\" in task_id:
                raise ValueError("Task IDs cannot contain path separators")
            tasks.append(
                dict(
                    task_id=task_id,
                    instruction=instruction,
                    category=category,
                    source=source_type,
                )
            )
    if not tasks:
        raise ValueError(f"No tasks found in {directory}")
    if len({t["task_id"] for t in tasks}) != len(tasks):
        raise ValueError("Duplicate task IDs")
    return tasks


def split_dataset(tasks, seed=0, validation_per_category=2):
    if validation_per_category < 1:
        raise ValueError("validation_per_category must be positive")
    categories = {}
    for task in tasks:
        categories.setdefault(task["category"], []).append(task)
    train, validation = [], []
    rng = random.Random(seed)
    for category, items in categories.items():
        if len(items) <= validation_per_category:
            raise ValueError(
                f"Category {category!r} needs at least {validation_per_category + 1} tasks"
            )
        rng.shuffle(items)
        validation.extend(items[:validation_per_category])
        train.extend(items[validation_per_category:])
    if not train:
        raise ValueError("Training split is empty")
    return train, validation


def repository_path(current_dir, value):
    return str(Path(current_dir) / value) if value else None


def resolve_train_dir(current_dir):
    explicit = os.environ.get("VLM_TRAIN_DIR")
    path = Path(repository_path(current_dir, explicit or "data/train_data"))
    if path.is_dir():
        return str(path)
    if explicit:
        raise FileNotFoundError(f"Configured training directory does not exist: {path}")
    return None


def load_seed_candidate(current_dir):
    explicit = os.environ.get("VLM_SEED_STRATEGY")
    path = Path(repository_path(current_dir, explicit or "configs/seed_candidate.json"))
    if not path.is_file():
        if explicit:
            raise FileNotFoundError(f"Configured seed file does not exist: {path}")
        return dict(seed_candidate)
    loaded = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict):
        raise ValueError(f"Seed strategy must be a JSON object: {path}")
    missing = set(seed_candidate).difference(loaded)
    if missing:
        raise ValueError(f"Seed strategy is missing components: {sorted(missing)}")
    if any(not isinstance(v, str) or not v.strip() for v in loaded.values()):
        raise ValueError("Seed components must be nonempty strings")
    return loaded
