"""向 Windows 注册截图快捷键，通过 Qt 窗口接收 WM_HOTKEY。"""
import ctypes
from contextlib import contextmanager
from ctypes import wintypes

from PySide6.QtCore import Signal
from PySide6.QtGui import QWindow


_user32 = ctypes.WinDLL("user32", use_last_error=True)
_register = _user32.RegisterHotKey
_register.argtypes = (wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT)
_register.restype = wintypes.BOOL
_unregister = _user32.UnregisterHotKey
_unregister.argtypes = (wintypes.HWND, ctypes.c_int)
_unregister.restype = wintypes.BOOL
_key_scan = _user32.VkKeyScanW
_key_scan.argtypes = (wintypes.WCHAR,)
_key_scan.restype = ctypes.c_short

_WM_HOTKEY = 0x0312
_MOD_NOREPEAT = 0x4000
_MODIFIERS = {"alt": 1, "ctrl": 2, "control": 2, "shift": 4, "win": 8, "windows": 8}
_KEYS = {
    "backspace": 0x08, "tab": 0x09, "enter": 0x0D, "return": 0x0D,
    "pause": 0x13, "esc": 0x1B, "escape": 0x1B, "space": 0x20,
    "page up": 0x21, "pgup": 0x21, "page down": 0x22, "pgdn": 0x22,
    "end": 0x23, "home": 0x24, "left": 0x25, "up": 0x26, "right": 0x27,
    "down": 0x28, "print screen": 0x2C, "insert": 0x2D, "ins": 0x2D,
    "delete": 0x2E, "del": 0x2E,
    **{f"f{i}": 0x6F + i for i in range(1, 25)},
}


class HotkeyError(ValueError):
    """快捷键格式有误，或 Windows 拒绝注册。"""


def _parse(shortcut):
    if not isinstance(shortcut, str):
        raise HotkeyError("请输入一个组合键，例如 Alt+Q 或 Ctrl+Alt+S。")
    modifiers = 0
    key = None
    for part in shortcut.casefold().split("+"):
        part = part.strip()
        if part in _MODIFIERS:
            modifiers |= _MODIFIERS[part]
        elif part and key is None:
            key = part
        else:
            raise HotkeyError("请输入一个组合键，例如 Alt+Q 或 Ctrl+Alt+S。")

    if key == "f12":
        raise HotkeyError("Windows 保留了 F12，请选择其他键。")
    if not modifiers and not (key in _KEYS and 0x70 <= _KEYS[key] <= 0x87):
        raise HotkeyError("请加入 Ctrl、Alt、Shift 或 Win，或使用一个功能键，例如 F8。")
    if key in _KEYS:
        return modifiers, _KEYS[key]
    if key and len(key) == 1 and key.isascii() and key.isalnum():
        return modifiers, ord(key.upper())
    if key == "plus":
        key = "+"
    if key and len(key) == 1 and key.isascii():
        scan = _key_scan(key)
        if scan >= 0 and scan >> 8 <= 7:
            # VkKeyScanW 的 Shift/Ctrl/Alt 位与 RegisterHotKey 的顺序不同。
            shift, ctrl, alt = (bool(scan & mask) for mask in (0x100, 0x200, 0x400))
            return modifiers | (shift * 4) | (ctrl * 2) | alt, scan & 0xFF
    raise HotkeyError("请使用字母、数字、常用符号或功能键等 Windows 按键。")


class GlobalHotkey(QWindow):
    activated = Signal()

    def __init__(self):
        super().__init__()
        self._id = None
        self._keys = None
        # 窗口保持隐藏；这样消息即使经过 Windows 的模态消息循环也有接收窗口。
        self._hwnd = self.winId()

    @contextmanager
    def bind(self, shortcut):
        """新组合键注册且设置保存后，再释放原组合键。"""
        keys = _parse(shortcut)
        if keys == self._keys:
            yield
            return
        hotkey_id = 2 if self._id == 1 else 1
        modifiers, vk = keys
        if not _register(self._hwnd, hotkey_id, modifiers | _MOD_NOREPEAT, vk):
            error = ctypes.get_last_error()
            if error == 1409:  # ERROR_HOTKEY_ALREADY_REGISTERED
                raise HotkeyError(f"快捷键 {shortcut.upper()} 已被占用，请换一个组合键。")
            raise HotkeyError(f"Windows 无法注册快捷键 {shortcut.upper()}（错误 {error}），请换一个组合键。")
        try:
            yield
        except BaseException:
            _unregister(self._hwnd, hotkey_id)
            raise
        self.release()
        self._id, self._keys = hotkey_id, keys

    def release(self):
        if self._id is not None:
            _unregister(self._hwnd, self._id)
            self._id = self._keys = None

    def nativeEvent(self, event_type, message):
        if event_type == b"windows_generic_MSG" and self._keys is not None:
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == _WM_HOTKEY and msg.wParam == self._id:
                # 同一 ID 可以被再次使用，忽略队列里旧组合键的消息。
                keys = (msg.lParam & 0xF, (msg.lParam >> 16) & 0xFFFF)
                if keys == self._keys:
                    self.activated.emit()
                return True, 0
        return False, 0
