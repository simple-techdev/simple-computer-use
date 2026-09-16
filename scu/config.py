"""Configuration for simple-computer-use.

Config file:  ~/.config/simple-computer-use/config.json
State dir:    ~/.config/simple-computer-use/

Environment variables override the config file:
    SCU_GROUND_PROVIDER   local | remote | none
    SCU_GROUND_URL        base URL of an OpenAI-compatible endpoint
    SCU_GROUND_MODEL      model name to request
    SCU_GROUND_API_KEY    api key for the endpoint (if any)
    SCU_GROUNDING_WIDTH   grounding model output coordinate width
    SCU_GROUNDING_HEIGHT  grounding model output coordinate height
"""

import json
import os
from typing import Any, Dict

APP_NAME = "simple-computer-use"
BASE_DIR = os.path.expanduser(os.path.join("~", ".config", APP_NAME))
CONFIG_PATH = os.path.join(BASE_DIR, "config.json")
STATE_PATH = os.path.join(BASE_DIR, "state.json")
OVERLAY_PID_PATH = os.path.join(BASE_DIR, "overlay.pid")
OVERLAY_LOG_PATH = os.path.join(BASE_DIR, "overlay.log")
GROUND_SERVER_LOG_PATH = os.path.join(BASE_DIR, "ground-server.log")
SHOTS_DIR = os.path.join(BASE_DIR, "screenshots")

DEFAULT_LOCAL_MODEL = "mlx-community/UI-TARS-1.5-7B-4bit"
DEFAULT_LOCAL_PORT = 8080
DEFAULT_LOCAL_URL = f"http://127.0.0.1:{DEFAULT_LOCAL_PORT}"

# Output coordinate resolution of the grounding model.
# UI-TARS-1.5-7B: 1920x1080. UI-TARS-72B: 1000x1000.
DEFAULT_GROUNDING_WIDTH = 1920
DEFAULT_GROUNDING_HEIGHT = 1080

DEFAULT_CONFIG: Dict[str, Any] = {
    "grounding": {
        "provider": "none",  # local | remote | none
        "url": "",
        "model": "",
        "api_key": "",
        "width": DEFAULT_GROUNDING_WIDTH,
        "height": DEFAULT_GROUNDING_HEIGHT,
        "local_model": DEFAULT_LOCAL_MODEL,
        "local_port": DEFAULT_LOCAL_PORT,
    }
}


def ensure_dirs() -> None:
    os.makedirs(BASE_DIR, exist_ok=True)
    os.makedirs(SHOTS_DIR, exist_ok=True)


def load_config() -> Dict[str, Any]:
    cfg = json.loads(json.dumps(DEFAULT_CONFIG))
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            user_cfg = json.load(f)
        for key, value in user_cfg.items():
            if isinstance(value, dict) and isinstance(cfg.get(key), dict):
                cfg[key].update(value)
            else:
                cfg[key] = value
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, OSError):
        pass

    env_map = {
        "SCU_GROUND_PROVIDER": ("grounding", "provider", str),
        "SCU_GROUND_URL": ("grounding", "url", str),
        "SCU_GROUND_MODEL": ("grounding", "model", str),
        "SCU_GROUND_API_KEY": ("grounding", "api_key", str),
        "SCU_GROUNDING_WIDTH": ("grounding", "width", int),
        "SCU_GROUNDING_HEIGHT": ("grounding", "height", int),
        "SCU_GROUND_LOCAL_MODEL": ("grounding", "local_model", str),
        "SCU_GROUND_LOCAL_PORT": ("grounding", "local_port", int),
    }
    for env_name, (section, key, conv) in env_map.items():
        val = os.environ.get(env_name)
        if val is not None and val != "":
            try:
                cfg[section][key] = conv(val)
            except ValueError:
                pass
    return cfg


def save_config(cfg: Dict[str, Any]) -> None:
    ensure_dirs()
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2)


def grounding_config() -> Dict[str, Any]:
    return load_config()["grounding"]
