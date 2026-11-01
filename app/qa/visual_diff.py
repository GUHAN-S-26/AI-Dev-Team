"""Deterministic screenshot comparison with explicit human acceptance."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def compare_images(baseline: Path, current: Path, diff_path: Path, threshold: float = 0.01) -> dict[str, Any]:
    from PIL import Image, ImageChops, ImageEnhance

    first = Image.open(baseline).convert("RGBA")
    second = Image.open(current).convert("RGBA")
    if first.size != second.size:
        return {"status": "FAIL", "reason": "image dimensions differ", "baseline": first.size, "current": second.size}
    difference = ImageChops.difference(first, second)
    pixels = list(difference.getdata())
    changed = sum(1 for pixel in pixels if max(pixel) > 8)
    ratio = changed / max(1, len(pixels))
    diff_path.parent.mkdir(parents=True, exist_ok=True)
    ImageEnhance.Contrast(difference).enhance(4.0).save(diff_path)
    return {"status": "PASS" if ratio <= threshold else "FAIL", "changed_pixel_ratio": ratio, "threshold": threshold, "diff": str(diff_path)}
