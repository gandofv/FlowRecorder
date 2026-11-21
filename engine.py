"""Recording and playback workers. All UI communication goes through emit()."""
import sys
import threading
import time
from queue import Empty, Queue

import desktop
from flow import capture_step, locate, patch_of

def countdown(stop, emit):
    for n in (3, 2, 1):
        emit("status", f"{n} 秒后开始，请切换到目标窗口")
        if stop.wait(1):
            return False
    return True


def record(stop, emit, expected=None, single=False):
    from pynput import mouse
    if not countdown(stop, emit):
        return
    app = desktop.front()
    if not app or (expected and expected != app):
        raise ValueError("前台应用与流程不符，请重新录制。")
    emit("app", app)
    latest = None
    lock = threading.Lock()
    clicks = Queue()
    def sample():
        if desktop.front() != app:
            return None
        started = time.monotonic()
        shot = desktop.screenshot()
        return (started, shot) if desktop.front() == app else None

    latest = sample()
    if latest is None:
        raise ValueError("请先打开目标应用。")
    def on_click(x, y, button, pressed):
        if pressed and button == mouse.Button.left and not stop.is_set():
            with lock:
                clicks.put((time.monotonic(), int(x), int(y), latest))
    previous = time.monotonic()
    with mouse.Listener(on_click=on_click) as listener:
        emit("ready", "录制中 · 按 F8 结束")
        count = 0
        while True:
            try:
                instant, x, y, frame = clicks.get(timeout=.05)
            except Empty:
                if stop.is_set():
                    return
                if not listener.running:
                    raise RuntimeError("鼠标监听已中断。")
                frame = sample()
                with lock:
                    latest = frame
                continue
            if frame is None or instant-frame[0] > 1.5:
                raise ValueError("点击前未取得清晰的目标窗口画面。请停留片刻后重新录制这一步。")
            step = capture_step(frame[1], x, y, min(3600, instant-previous))
            step["name"] = f"点击 {count+1}"
            emit("step", step)
            previous = instant
            count += 1
            if single or count == 1000:
                return


def play(doc, stop, emit):
    if sys.platform != doc["platform"]:
        raise ValueError("请在录制此脚本的操作系统上回放。")
    if not countdown(stop, emit):
        return
    for i, step in enumerate(doc["steps"], 1):
        emit("progress", (i, step["name"]))
        if stop.wait(step["delay"]):
            return
        patch = patch_of(step)
        deadline = time.monotonic()+10
        while not stop.is_set():
            if desktop.front() != doc["app"]:
                raise ValueError(f"第 {i} 步停止：目标应用不在前台。")
            pos = locate(desktop.screenshot(), patch, step["offset"])
            if pos is not None:
                if stop.is_set():
                    return
                if desktop.front() != doc["app"]:
                    raise ValueError(f"第 {i} 步停止：前台应用已切换。")
                if not desktop.target_at(pos):
                    raise ValueError(f"第 {i} 步停止：按钮被其他窗口遮挡。")
                if stop.is_set():
                    return
                desktop.click(pos)
                break
            if time.monotonic() >= deadline:
                raise ValueError(f"第 {i} 步未找到唯一匹配。请检查起始页面、缩放或重新录制此步。")
            stop.wait(.2)
