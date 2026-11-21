"""Native foreground identity and primary display in logical mouse coordinates."""
import sys
import ctypes

if sys.platform == "win32":
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        ctypes.windll.user32.SetProcessDPIAware()

import pyautogui as gui
from PIL import Image


def front():
    if sys.platform == "darwin":
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        return str(app.bundleIdentifier() or app.executableURL().path()) if app else ""
    from ctypes import wintypes as wt
    user = ctypes.windll.user32
    kernel = ctypes.windll.kernel32
    user.GetForegroundWindow.restype = wt.HWND
    user.GetWindowThreadProcessId.argtypes = [wt.HWND, ctypes.POINTER(wt.DWORD)]
    pid = wt.DWORD()
    user.GetWindowThreadProcessId(user.GetForegroundWindow(), ctypes.byref(pid))
    kernel.OpenProcess.restype = wt.HANDLE
    handle = kernel.OpenProcess(0x1000, False, pid.value)
    if not handle:
        return ""
    try:
        buf = ctypes.create_unicode_buffer(32768)
        size = wt.DWORD(len(buf))
        if kernel.QueryFullProcessImageNameW(wt.HANDLE(handle), 0, buf, ctypes.byref(size)):
            return buf.value.casefold()
        return ""
    finally:
        kernel.CloseHandle(wt.HANDLE(handle))


def screenshot():
    image = gui.screenshot().convert("RGB")
    size = tuple(gui.size())
    if image.size != size:
        image = image.resize(size, Image.Resampling.LANCZOS)
    return image


def click(point):
    gui.click(*point)


def target_at(point):
    """Verify that the clickable window at the matched point belongs to the foreground app."""
    x, y = point
    if sys.platform == "darwin":
        import Quartz as q
        from AppKit import NSWorkspace
        app = NSWorkspace.sharedWorkspace().frontmostApplication()
        if app is None:
            return False
        pid = app.processIdentifier()
        windows = q.CGWindowListCopyWindowInfo(q.kCGWindowListOptionOnScreenOnly | q.kCGWindowListExcludeDesktopElements, 0)
        for window in windows or ():
            b = window.get(q.kCGWindowBounds, {})
            if window.get(q.kCGWindowAlpha, 1) <= 0 or "X" not in b:
                continue
            if b["X"] <= x < b["X"]+b["Width"] and b["Y"] <= y < b["Y"]+b["Height"]:
                return window.get(q.kCGWindowOwnerPID) == pid
        return False
    from ctypes import wintypes as wt
    user = ctypes.windll.user32
    user.WindowFromPoint.argtypes = [wt.POINT]
    user.WindowFromPoint.restype = wt.HWND
    hit = user.WindowFromPoint(wt.POINT(x,y))
    foreground = user.GetForegroundWindow()
    a, b = wt.DWORD(), wt.DWORD()
    user.GetWindowThreadProcessId(hit,ctypes.byref(a))
    user.GetWindowThreadProcessId(foreground,ctypes.byref(b))
    return bool(a.value and a.value == b.value)
