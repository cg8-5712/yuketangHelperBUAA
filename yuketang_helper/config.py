"""Runtime paths and configuration validation."""

import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"
AI_CONFIG_PATH = PROJECT_ROOT / "config.json"
QUESTION_BANK_PATH = PROJECT_ROOT / "question_bank.sqlite3"
REQUEST_TIMEOUT = (3, 15)


def load_ai_config(path=AI_CONFIG_PATH):
    with Path(path).open(encoding="utf-8") as config_file:
        config = json.load(config_file)
    required = ("base_url", "key", "model", "system_prompt")
    missing = [key for key in required if not isinstance(config.get(key), str) or not config[key].strip()]
    if missing:
        raise ValueError(f"config.json 缺少配置项：{', '.join(missing)}")
    return config
