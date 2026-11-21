"""Portable visual anchors and versioned workflow files."""
import base64
import io
import json
import math
import os
import tempfile
from pathlib import Path

import numpy as np
from PIL import Image


def capture_step(screen, x, y, delay):
    w, h = screen.size
    if not (0 <= x < w and 0 <= y < h):
        raise ValueError("请在主显示器内点击。")
    left, top = max(0, x - 52), max(0, y - 28)
    patch = screen.crop((left, top, min(w, x + 53), min(h, y + 29))).convert("RGB")
    buffer = io.BytesIO()
    patch.save(buffer, format="PNG")
    return dict(name="点击", delay=round(delay, 2), offset=[x-left, y-top],
                image=base64.b64encode(buffer.getvalue()).decode("ascii"))


def patch_of(step):
    raw = base64.b64decode(step["image"], validate=True)
    with Image.open(io.BytesIO(raw)) as im:
        if im.format != "PNG" or not (1 <= im.width <= 105 and 1 <= im.height <= 57):
            raise ValueError("步骤定位图尺寸无效。")
        return im.convert("RGB")


def locate(screen, patch, offset):
    """Filter translations using distinctive pixels, then verify the whole RGB crop."""
    scene = np.asarray(screen.convert("RGB"), dtype=np.int16)
    template = np.asarray(patch, dtype=np.int16)
    h, w = template.shape[:2]
    rows, cols = scene.shape[0]-h+1, scene.shape[1]-w+1
    if min(rows, cols) <= 0:
        return None
    # Sample across tiles so that one repeated letter cannot dominate.
    background = np.median(template.reshape(-1, 3), axis=0)
    contrast = np.max(abs(template-background), axis=2)
    anchors = []
    for y in range(0, h, 12):
        for x in range(0, w, 16):
            tile = contrast[y:y+12, x:x+16]
            dy, dx = np.unravel_index(tile.argmax(), tile.shape)
            anchors.append((tile[dy, dx], y+dy, x+dx))
    anchors.sort(reverse=True)
    if anchors[0][0] < 25:
        return None
    _, y, x = anchors[0]
    color = template[y, x]
    nearby = scene[y:y+rows, x:x+cols]
    ys, xs = np.nonzero(np.max(abs(nearby-color), axis=2) <= 18)
    for _, y, x in anchors[1:]:
        keep = np.max(abs(scene[ys+y, xs+x]-template[y, x]), axis=1) <= 22
        xs, ys = xs[keep], ys[keep]
        if not len(xs):
            return None
    if len(xs) > 500:
        return None
    matches = []
    for x, y in zip(xs, ys):
        error = abs(scene[y:y+h, x:x+w]-template)
        if error.mean() < 5 and np.mean(error.max(axis=2) > 25) < .04:
            matches.append((error.mean(), int(x), int(y)))
    if not matches:
        return None
    _, bx, by = min(matches)
    if any(abs(x-bx) > 3 or abs(y-by) > 3 for _, x, y in matches):
        return None
    return bx+offset[0], by+offset[1]


def validate(doc):
    if doc["version"] != 1 or doc["platform"] not in ("win32", "darwin"):
        raise ValueError("脚本格式或系统标识无效。")
    if not isinstance(doc["app"], str) or not doc["app"]:
        raise ValueError("缺失目标应用。")
    steps = doc["steps"]
    if not isinstance(steps, list) or not 1 <= len(steps) <= 1000:
        raise ValueError("脚本需要包含 1 至 1000 步。")
    for step in steps:
        patch = patch_of(step)
        dx, dy = step["offset"]
        if not (type(dx) is int and type(dy) is int and 0 <= dx < patch.width and 0 <= dy < patch.height):
            raise ValueError("点击偏移无效。")
        delay = step["delay"]
        if not isinstance(delay, (int, float)) or not math.isfinite(delay) or not 0 <= delay <= 3600:
            raise ValueError("等待时间应为 0 至 3600 秒。")
        if not isinstance(step["name"], str) or not step["name"].strip():
            raise ValueError("步骤名称不能为空。")
    return doc


def load(path):
    if Path(path).stat().st_size > 64*1024*1024:
        raise ValueError("脚本文件过大。")
    return validate(json.loads(Path(path).read_text(encoding="utf-8")))


def save(path, doc):
    validate(doc)
    with tempfile.NamedTemporaryFile(dir=Path(path).parent, delete=False) as tmp:
        temp = Path(tmp.name)
    try:
        temp.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
