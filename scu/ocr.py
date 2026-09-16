"""OCR helpers: word-level bounding boxes and phrase lookup.

Used by `scu find-text` and as a fallback ground for `click "some text"` when
no grounding model is configured. Ported from Agent-S's OCR pipeline, with the
LLM phrase->word step replaced by deterministic fuzzy matching.
"""

import difflib
import io
import re
from typing import Dict, List, Optional

from PIL import Image

try:
    import pytesseract
    from pytesseract import Output

    _HAS_TESS = True
except ImportError:
    _HAS_TESS = False

_CLEAN = re.compile(r"^[^a-zA-Z0-9\s.,!?;:\-+@#$%&*()\[\]{}'\"/\\]+|[^a-zA-Z0-9\s.,!?;:\-+@#$%&*()\[\]{}'\"/\\]+$")


def available() -> bool:
    if not _HAS_TESS:
        return False
    try:
        pytesseract.get_tesseract_version()
        return True
    except Exception:
        return False


def word_boxes(png_bytes: bytes) -> List[Dict]:
    """Word-level boxes in image PIXELS."""
    if not available():
        raise RuntimeError(
            "tesseract not available — install it (macOS: `brew install tesseract`)"
        )
    image = Image.open(io.BytesIO(png_bytes))
    data = pytesseract.image_to_data(image, output_type=Output.DICT)
    words = []
    for i, raw in enumerate(data["text"]):
        text = _CLEAN.sub("", raw or "")
        if not text:
            continue
        words.append(
            {
                "id": len(words),
                "text": text,
                "line": (
                    data["block_num"][i],
                    data["par_num"][i],
                    data["line_num"][i],
                ),
                "left": data["left"][i],
                "top": data["top"][i],
                "w": data["width"][i],
                "h": data["height"][i],
                "conf": float(data["conf"][i]),
            }
        )
    return words


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower()).strip()


def find(
    phrase: str, png_bytes: bytes, limit: int = 5
) -> List[Dict]:
    """Locate `phrase` in the screenshot. Returns matches with centers as
    0-1 image fractions (fx, fy) plus pixel boxes, best match first."""
    img = Image.open(io.BytesIO(png_bytes))
    iw, ih = img.size
    words = word_boxes(png_bytes)
    if not words:
        return []

    # Group words into lines so multi-word phrases match contiguous spans.
    lines: Dict[tuple, List[Dict]] = {}
    for w in words:
        lines.setdefault(w["line"], []).append(w)

    target = _norm(phrase)
    target_words = target.split()
    matches = []

    for _, ws in lines.items():
        ws.sort(key=lambda w: w["left"])
        texts = [w["text"] for w in ws]
        n = len(target_words)
        # Windows of len(target_words) +- 1 around each start position.
        for start in range(len(ws)):
            for size in {n, n + 1, max(1, n - 1)}:
                end = start + size
                if end > len(ws):
                    continue
                span = ws[start:end]
                joined = _norm(" ".join(t["text"] for t in span))
                score = difflib.SequenceMatcher(None, joined, target).ratio()
                if joined == target:
                    score = 1.0
                if score < 0.6:
                    continue
                x1 = min(w["left"] for w in span)
                y1 = min(w["top"] for w in span)
                x2 = max(w["left"] + w["w"] for w in span)
                y2 = max(w["top"] + w["h"] for w in span)
                cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
                matches.append(
                    {
                        "text": " ".join(t["text"] for t in span),
                        "score": round(score, 3),
                        "fx": cx / iw,
                        "fy": cy / ih,
                        "x_px": int(cx),
                        "y_px": int(cy),
                        "box": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
                    }
                )

    # Deduplicate overlapping spans, keep best scores.
    matches.sort(key=lambda m: -m["score"])
    out, seen = [], set()
    for m in matches:
        key = (round(m["fx"], 3), round(m["fy"], 3))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
        if len(out) >= limit:
            break
    return out
