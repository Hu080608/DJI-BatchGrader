"""Native Windows drag-and-drop for selected Tk widgets.

The native drop callback must never call Tk APIs directly: doing so from inside
a Windows WndProc can re-enter Tk's event loop and freeze the application.  This
module only enqueues dropped paths into a thread-safe queue; the GUI polls that
queue from Tk's normal after() callback.
"""
from __future__ import annotations

import ctypes
import os
import queue
from pathlib import Path
from typing import Callable

WM_DROPFILES = 0x0233
GWLP_WNDPROC = -4


class WindowsDropTarget:
    def __init__(self, widget, drop_queue: "queue.Queue[list[Path]]"):
        if os.name != "nt":
            raise OSError("本版本的拖拽上传仅支持 Windows")
        self.widget = widget
        self.drop_queue = drop_queue
        self.hwnd = int(widget.winfo_id())
        self._old_proc = 0
        self._new_proc = None
        self._active = False

        shell32 = ctypes.windll.shell32
        user32 = ctypes.windll.user32
        shell32.DragAcceptFiles.argtypes = [ctypes.c_void_p, ctypes.c_bool]
        shell32.DragAcceptFiles.restype = None
        shell32.DragQueryFileW.argtypes = [
            ctypes.c_void_p, ctypes.c_uint, ctypes.c_wchar_p, ctypes.c_uint
        ]
        shell32.DragQueryFileW.restype = ctypes.c_uint
        shell32.DragFinish.argtypes = [ctypes.c_void_p]
        shell32.DragFinish.restype = None

        self._WNDPROC = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t,
            ctypes.c_void_p,
            ctypes.c_uint,
            ctypes.c_size_t,
            ctypes.c_ssize_t,
        )

        def _wnd_proc(hwnd, msg, wparam, lparam):
            if msg == WM_DROPFILES:
                paths: list[Path] = []
                try:
                    count = int(shell32.DragQueryFileW(wparam, 0xFFFFFFFF, None, 0))
                    for index in range(count):
                        length = int(shell32.DragQueryFileW(wparam, index, None, 0))
                        buffer = ctypes.create_unicode_buffer(length + 1)
                        shell32.DragQueryFileW(wparam, index, buffer, length + 1)
                        if buffer.value:
                            paths.append(Path(buffer.value))
                except Exception:
                    paths = []
                finally:
                    try:
                        shell32.DragFinish(wparam)
                    except Exception:
                        pass
                if paths:
                    # IMPORTANT: no Tk calls here.  Only a thread-safe queue put.
                    self.drop_queue.put(paths)
                return 0
            if self._old_proc:
                return user32.CallWindowProcW(
                    ctypes.c_void_p(self._old_proc), hwnd, msg, wparam, lparam
                )
            return 0

        self._new_proc = self._WNDPROC(_wnd_proc)
        user32.SetWindowLongPtrW.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
        user32.SetWindowLongPtrW.restype = ctypes.c_void_p
        user32.CallWindowProcW.argtypes = [
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_uint,
            ctypes.c_size_t, ctypes.c_ssize_t,
        ]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t
        self._old_proc = int(user32.SetWindowLongPtrW(
            ctypes.c_void_p(self.hwnd), GWLP_WNDPROC, self._new_proc
        ) or 0)
        shell32.DragAcceptFiles(ctypes.c_void_p(self.hwnd), True)
        self._active = True

    def close(self) -> None:
        if not self._active or not self.hwnd:
            return
        try:
            ctypes.windll.shell32.DragAcceptFiles(ctypes.c_void_p(self.hwnd), False)
        except Exception:
            pass
        try:
            if self._old_proc:
                ctypes.windll.user32.SetWindowLongPtrW(
                    ctypes.c_void_p(self.hwnd), GWLP_WNDPROC,
                    ctypes.c_void_p(self._old_proc)
                )
        except Exception:
            pass
        self._active = False


def enable_file_drop(
    widgets,
    drop_queue: "queue.Queue[list[Path]]",
) -> list[WindowsDropTarget]:
    """Register Tk widgets as native file-drop targets.

    The callback-free design means the native WndProc only enqueues paths;
    the Tk main loop later consumes them safely.
    """
    if os.name != "nt":
        return []
    if not isinstance(widgets, (list, tuple)):
        widgets = [widgets]
    targets: list[WindowsDropTarget] = []
    for widget in widgets:
        try:
            targets.append(WindowsDropTarget(widget, drop_queue))
        except Exception:
            continue
    return targets
