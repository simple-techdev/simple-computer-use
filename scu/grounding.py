"""Visual grounding: natural-language element description -> screen position.

Wraps a point-output VLM (UI-TARS family) behind an OpenAI-compatible
/v1/chat/completions endpoint. Two providers:

  local   - bundled mlx-vlm server on this Mac (Apple Silicon), auto-started
  remote  - any OpenAI-compatible endpoint (HF inference endpoint, vLLM,
            Parasail, OpenRouter, ...)

ground() returns the target as a 0-1 fraction of the supplied screenshot, so
the caller maps it into global screen points for whatever display the image
came from.
"""

import base64
import platform
import re
import subprocess
import sys
import time
from typing import Optional, Tuple

import requests

from scu import config as cfgmod

GROUND_PROMPT = "Query:{q}\nOutput only the coordinate of one point in your response.\n"


class GroundingError(RuntimeError):
    pass


def local_supported() -> bool:
    """Local bundled grounding requires Apple Silicon + Python>=3.10
    (mlx-vlm's requirement)."""
    return (
        sys.platform == "darwin"
        and platform.machine() == "arm64"
        and sys.version_info >= (3, 10)
    )


def local_installed() -> bool:
    try:
        import mlx_vlm  # noqa: F401

        return True
    except ImportError:
        return False


def _server_alive(url: str) -> bool:
    for path in ("/health", "/v1/models", "/models"):
        try:
            r = requests.get(url.rstrip("/") + path, timeout=2)
            if r.status_code < 500:
                return True
        except requests.RequestException:
            continue
    return False


def ensure_local_server(cfg: dict, wait_s: int = 120) -> str:
    """Start the bundled mlx-vlm server if needed; return its base URL."""
    url = f"http://127.0.0.1:{cfg.get('local_port', cfgmod.DEFAULT_LOCAL_PORT)}"
    if _server_alive(url):
        return url
    if not local_installed():
        raise GroundingError(
            "local grounding needs mlx-vlm: pip install 'simple-computer-use[local]' "
            "or run `scu install` and pick the local option"
        )
    cfgmod.ensure_dirs()
    log = open(cfgmod.GROUND_SERVER_LOG_PATH, "ab")
    model = cfg.get("local_model") or cfgmod.DEFAULT_LOCAL_MODEL
    # mlx_vlm.server can lazy-load the model named in each request, but we pass
    # --model so the first request doesn't pay the full load cost.
    cmd = [
        sys.executable,
        "-m",
        "mlx_vlm.server",
        "--model",
        model,
        "--host",
        "127.0.0.1",
        "--port",
        str(cfg.get("local_port", cfgmod.DEFAULT_LOCAL_PORT)),
    ]
    subprocess.Popen(
        cmd, stdout=log, stderr=subprocess.STDOUT, start_new_session=True
    )
    deadline = time.time() + wait_s
    while time.time() < deadline:
        if _server_alive(url):
            return url
        time.sleep(1.0)
    raise GroundingError(
        f"local grounding server did not come up in {wait_s}s; "
        f"see {cfgmod.GROUND_SERVER_LOG_PATH}"
    )


def ground(
    ref_expr: str, image_png: bytes, cfg: Optional[dict] = None
) -> Tuple[float, float, str]:
    """Locate `ref_expr` in the screenshot.

    Returns (fx, fy, raw_text): position as a 0-1 fraction of the image plus
    the model's raw response.
    """
    cfg = cfg or cfgmod.grounding_config()
    provider = cfg.get("provider", "none")

    if provider == "local":
        base_url = ensure_local_server(cfg)
        model = cfg.get("local_model") or cfgmod.DEFAULT_LOCAL_MODEL
    elif provider == "remote":
        base_url = cfg.get("url") or ""
        model = cfg.get("model") or ""
        if not base_url:
            raise GroundingError(
                "grounding provider=remote but no url configured; "
                "run `scu install` or set SCU_GROUND_URL"
            )
    else:
        raise GroundingError(
            "no grounding model configured; use --at x,y, `scu find-text`, "
            "or run `scu install` to set up local/remote grounding"
        )

    b64 = base64.b64encode(image_png).decode("ascii")
    payload = {
        "model": model or "tgi",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "image_url",
                        "image_url": {"url": f"data:image/png;base64,{b64}"},
                    },
                    {"type": "text", "text": GROUND_PROMPT.format(q=ref_expr)},
                ],
            }
        ],
        "max_tokens": 64,
        "temperature": 0,
        "stream": False,
    }
    headers = {"Content-Type": "application/json"}
    api_key = cfg.get("api_key") or ""
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        r = requests.post(
            base_url.rstrip("/") + "/v1/chat/completions",
            json=payload,
            headers=headers,
            timeout=600,  # local server may be loading the model on first call
        )
        r.raise_for_status()
        text = r.json()["choices"][0]["message"]["content"]
    except requests.RequestException as e:
        raise GroundingError(f"grounding request failed: {e}") from e
    except (KeyError, IndexError, ValueError) as e:
        raise GroundingError(f"bad grounding response: {e}") from e

    nums = re.findall(r"-?\d+\.?\d*", text or "")
    if len(nums) < 2:
        raise GroundingError(f"grounding model returned no coordinates: {text!r}")
    gx, gy = float(nums[0]), float(nums[1])

    gw = float(cfg.get("width") or cfgmod.DEFAULT_GROUNDING_WIDTH)
    gh = float(cfg.get("height") or cfgmod.DEFAULT_GROUNDING_HEIGHT)
    fx = min(max(gx / gw, 0.0), 1.0)
    fy = min(max(gy / gh, 0.0), 1.0)
    return fx, fy, (text or "").strip()
