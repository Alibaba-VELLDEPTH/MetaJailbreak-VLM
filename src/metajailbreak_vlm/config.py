import argparse
import os


def load_dotenv(path):
    """Load simple KEY=VALUE pairs without requiring python-dotenv."""
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as file:
        for raw_line in file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if (
                len(value) >= 2
                and value[0] == value[-1]
                and value[0] in {chr(34), chr(39)}
            ):
                value = value[1:-1]
            os.environ.setdefault(key, value)


def _env(name, default=None):
    value = os.environ.get(name, default)
    if value is None:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def build_configuration():
    return argparse.Namespace(
        attacker_model_name=os.environ.get("ATTACKER_MODEL_NAME", "glm-4.6"),
        attacker_model_url=os.environ.get(
            "ATTACKER_MODEL_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        attacker_model_key=os.environ.get("ATTACKER_MODEL_API_KEY"),
        victim_model_name=os.environ.get("VICTIM_MODEL_NAME", "gpt-4o"),
        victim_model_url=os.environ.get(
            "VICTIM_MODEL_URL", "https://api.vectorengine.ai/v1"
        ),
        victim_model_key=os.environ.get("VICTIM_MODEL_API_KEY"),
        feedback_model_name=os.environ.get("FEEDBACK_MODEL_NAME", "gpt-4o"),
        feedback_model_url=os.environ.get(
            "FEEDBACK_MODEL_URL", "https://api.vectorengine.ai/v1"
        ),
        feedback_model_key=os.environ.get("FEEDBACK_MODEL_API_KEY"),
        Image_Generation_Model=os.environ.get("IMAGE_MODEL_NAME", "z-image-turbo"),
        Image_Generation_Model_base_url=os.environ.get(
            "IMAGE_MODEL_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
        ),
        Image_Generation_Model_api_key=os.environ.get("IMAGE_MODEL_API_KEY"),
    )


def validate_api_configuration(args):
    required = {
        "ATTACKER_MODEL_API_KEY": args.attacker_model_key,
        "VICTIM_MODEL_API_KEY": args.victim_model_key,
        "FEEDBACK_MODEL_API_KEY": args.feedback_model_key,
        "IMAGE_MODEL_API_KEY": args.Image_Generation_Model_api_key,
    }
    missing = [
        name
        for name, value in required.items()
        if not value or value.startswith("PASTE_YOUR_")
    ]
    if missing:
        env_path = os.path.join(os.getcwd(), ".env")
        raise RuntimeError(
            "API credentials are missing or still use placeholder values.\n"
            f"Edit this local file: {env_path}\n"
            "Set: " + ", ".join(missing) + "\n"
            "Do not commit or share .env."
        )


def parse_positive_int(name, default, minimum):
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value < minimum:
        raise ValueError(f"{name} must be >= {minimum}")
    return value
