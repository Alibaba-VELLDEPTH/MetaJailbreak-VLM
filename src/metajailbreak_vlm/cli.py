"""Command-line interface. Relative paths are resolved from the working directory."""

import argparse
import os
import sys

from .config import (
    build_configuration,
    load_dotenv,
    parse_positive_int,
    validate_api_configuration,
)


def main(argv=None):
    parser = argparse.ArgumentParser(description="MetaJailbreak-VLM evaluation runner")
    parser.add_argument(
        "--env-file", default=".env", help="Configuration file (default: .env)"
    )
    parser.add_argument("--train-dir", help="Directory containing task JSON files")
    parser.add_argument("--seed-strategy", help="Seed JSON file")
    parser.add_argument("--output", help="Output strategy JSON path")
    parser.add_argument(
        "--max-metric-calls",
        type=int,
        help="Metric budget (not an API request or cost limit)",
    )
    parser.add_argument("--minibatch-size", type=int)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--check",
        action="store_true",
        help="Validate local configuration and data; no API calls",
    )
    mode.add_argument(
        "--smoke-test",
        action="store_true",
        help="Run an offline optimizer check with synthetic inputs",
    )
    options = parser.parse_args(argv)
    if options.smoke_test:
        from .smoke import run

        run()
        return 0
    load_dotenv(options.env_file)
    for option, name in [
        ("train_dir", "VLM_TRAIN_DIR"),
        ("seed_strategy", "VLM_SEED_STRATEGY"),
        ("output", "VLM_OUTPUT_STRATEGY"),
        ("max_metric_calls", "VLM_MAX_METRIC_CALLS"),
        ("minibatch_size", "VLM_MINIBATCH_SIZE"),
    ]:
        value = getattr(options, option)
        if value is not None:
            os.environ[name] = str(value)
    try:
        validate_api_configuration(build_configuration())
        parse_positive_int("VLM_MAX_METRIC_CALLS", 156, 0)
        parse_positive_int("VLM_MINIBATCH_SIZE", 3, 1)
        from .data import (
            load_dataset_from_directory,
            load_seed_candidate,
            resolve_train_dir,
            split_dataset,
        )

        directory = resolve_train_dir(os.getcwd())
        if directory is None:
            raise FileNotFoundError(
                "Set --train-dir or VLM_TRAIN_DIR to your task directory."
            )
        train, validation = split_dataset(
            load_dataset_from_directory(directory, "Train")
        )
        load_seed_candidate(os.getcwd())
        if options.check:
            print(
                f"Local configuration OK: {len(train)} train, {len(validation)} validation. API connectivity has not been tested."
            )
            return 0
        from .logging import Logger
        from .runner import main as run

        stdout, stderr = sys.stdout, sys.stderr
        logger = Logger()
        try:
            sys.stdout = sys.stderr = logger
            run()
        finally:
            sys.stdout, sys.stderr = stdout, stderr
            logger.close()
        return 0
    except (ValueError, RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
