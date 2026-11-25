"""程序入口：启动系统托盘，注册截图快捷键，调度录音转写和流式回答。"""
import sys

import keyboard
from PySide6.QtCore import QObject, QThread, Qt, Signal
from PySide6.QtGui import QColor, QCursor, QFont, QIcon, QPainter, QPixmap, QGuiApplication
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

import autostart
import config
from api import ApiError, prompt_for, stream_chat, transcribe_audio
from overlay import SnipOverlay
from result_window import ResultWindow
from settings_dialog import SettingsDialog
from voice_input import Recording, speech_wav


class HotkeyBridge(QObject):
    """keyboard 库的回调发生在它自己的监听线程里，通过信号转回 Qt 主线程。"""
    triggered = Signal()


class AnswerWorker(QThread):
    """在后台线程里调用接口，把逐段到达的回答发回主线程。"""
    chunk = Signal(str)
    reasoning = Signal(str)
    searching = Signal()

    def __init__(self, api_key, prompt, jpeg_bytes, thinking, *, web_search, history,
                 question, initial_instruction, parent=None):
        super().__init__(parent)
        self._args = api_key, prompt, jpeg_bytes, thinking
        self._kwargs = dict(web_search=web_search, history=history, question=question,
                            initial_instruction=initial_instruction)
        self.error = None

    def run(self):
        try:
            for kind, piece in stream_chat(*self._args, **self._kwargs):
                if kind == "reasoning":
                    self.reasoning.emit(piece)
                elif kind == "searching":
                    self.searching.emit()
                else:
                    self.chunk.emit(piece)
        except ApiError as e:
            self.error = str(e)
        except Exception:
            self.error = "处理回答时发生错误，请重试。"


class VoiceWorker(QThread):
    def __init__(self, api_key, recording, parent=None):
        super().__init__(parent)
        self._api_key = api_key
        self._recording = recording
        self.text = ""
        self.error = ""

    def run(self):
        try:
            wav_bytes = speech_wav(self._recording)
            if wav_bytes is not None:
                self.text = transcribe_audio(self._api_key, wav_bytes)
        except ApiError as exc:
            self.error = str(exc)
        except Exception:
            self.error = "处理语音时发生错误。"
        finally:
            self._recording = None


def make_tray_icon():
    """程序自己画一个托盘图标：蓝底白字一个“题”。"""
    pm = QPixmap(64, 64)
    pm.fill(Qt.transparent)
    p = QPainter(pm)
    p.setRenderHint(QPainter.Antialiasing)
    p.setPen(Qt.NoPen)
    p.setBrush(QColor(0, 120, 215))
    p.drawEllipse(3, 3, 58, 58)
    p.setPen(QColor("white"))
    f = QFont("Microsoft YaHei", 26, QFont.Bold)
    p.setFont(f)
    p.drawText(pm.rect(), Qt.AlignCenter, "题")
    p.end()
    return QIcon(pm)


class App(QObject):
    def __init__(self, qt_app):
        super().__init__(qt_app)
        self.qt_app = qt_app
        self.cfg = config.load()

        self.overlay = None
        self.result_window = None
        self.worker = None
        self.settings_dialog = None
        self._hotkey_handle = None
        self._jpeg = None
        self._prompt = None
        self._initial_instruction = ""

        # 托盘图标和菜单（要先建好，注册快捷键失败时才有地方提示）
        self.tray = QSystemTrayIcon(make_tray_icon())
        self.tray_menu = menu = QMenu()
        self.snip_action = menu.addAction("截图提问（%s）" % self.cfg["hotkey"], self.start_snip)
        self.conversation_action = menu.addAction("查看当前对话", self._show_conversation)
        self.conversation_action.setEnabled(False)
        menu.addAction("设置…", self.open_settings)
        menu.addSeparator()
        menu.addAction("退出", self.quit)
        self.tray.setContextMenu(menu)
        self.tray.setToolTip("截图解题")
        self.tray.show()

        # 快捷键回调 → 主线程信号 → 开始截图
        self.bridge = HotkeyBridge()
        self.bridge.triggered.connect(self.start_snip)
        self.register_hotkey()

        # 第一次使用且还没填密钥时，主动弹出设置窗口
        if not self.cfg.get("api_key"):
            self.tray.showMessage(
                "截图解题",
                "请先在设置里填入你的 DeepSeek API 密钥。",
                QSystemTrayIcon.Information,
                5000,
            )
            self.open_settings()

        # 开机自启：如果配置里开了，就刷新一遍登记。
        # 好处是 exe 被移动或改名后，登记里的旧路径会自动修正，自启不会失效。
        if self.cfg.get("autostart"):
            try:
                autostart.set_enabled(True)
            except OSError:
                pass  # 刷新失败不影响正常使用，下次保存设置时会再尝试

    # ---------- 快捷键 ----------

    def register_hotkey(self):
        # keyboard 库的 remove_all_hotkeys 在监听器未启动时会崩溃，
        # 所以改为记录本次注册的句柄，单独移除
        if self._hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self._hotkey_handle)
            except (ValueError, KeyError):
                pass
            self._hotkey_handle = None
        try:
            self._hotkey_handle = keyboard.add_hotkey(
                self.cfg.get("hotkey", "alt+q"),
                lambda: self.bridge.triggered.emit(),
            )
        except Exception as e:
            self.tray.showMessage("截图解题", "快捷键注册失败：" + repr(e),
                                  QSystemTrayIcon.Warning, 5000)

    # ---------- 截图 ----------

    def start_snip(self):
        if self.overlay is not None:  # 已经在框选过程中，忽略重复触发
            return
        if self.worker is not None:
            self.tray.showMessage("截图解题", "当前请求仍在处理中，请稍后再截图。",
                                  QSystemTrayIcon.Information, 3000)
            return
        if not self.cfg.get("api_key"):
            self.open_settings()
            return

        # 在鼠标所在的屏幕上截图框选（单显示器场景下就是主屏）
        screen = QGuiApplication.screenAt(QCursor.pos()) or QGuiApplication.primaryScreen()
        self.overlay = SnipOverlay(screen, voice_input=self.cfg.get("voice_input", False))
        self.overlay.selected.connect(self.on_selected)
        self.overlay.cancelled.connect(self.on_snip_done)
        self.overlay.start()

    def on_snip_done(self):
        if self.overlay is not None:
            self.overlay.deleteLater()
            self.overlay = None

    def on_selected(self, jpeg_bytes, recording, capture_error):
        self.on_snip_done()
        if self.result_window is None:
            self.result_window = ResultWindow()
            self.result_window.send_requested.connect(self._request_answer)
            self.result_window.instruction_requested.connect(self._submit_instruction)
            self.result_window.retry_requested.connect(self._retry_answer)
        style = self.cfg.get("style", "explain")
        modes = self.cfg["custom_modes"]
        mode_name = next((mode["name"] for mode in modes if mode["id"] == style),
                         config.BUILTIN_MODES.get(style, config.BUILTIN_MODES["explain"]))
        self._jpeg = jpeg_bytes
        self._prompt = prompt_for(style, modes)
        self._initial_instruction = ""
        self.result_window.begin(mode_name)
        self.conversation_action.setEnabled(True)
        self.result_window.reveal()

        if capture_error:
            self.result_window.show_voice_error(capture_error)
        elif recording is None:
            self._request_answer(None)
        else:
            self.result_window.show_transcribing()
            self.worker = VoiceWorker(self.cfg["api_key"], recording, self)
            self.worker.finished.connect(self._voice_finished)
            self.worker.start()

    def _voice_finished(self):
        worker, self.worker = self.worker, None
        if worker.error:
            self.result_window.show_voice_error(worker.error)
        else:
            self._submit_instruction(worker.text, from_voice=True)
        worker.deleteLater()

    def _submit_instruction(self, text, *, from_voice=False):
        self._initial_instruction = text
        self.result_window.set_initial_instruction(text, from_voice=from_voice)
        self._request_answer(None)

    def _show_conversation(self):
        if self.result_window is not None:
            self.result_window.reveal()

    def _retry_answer(self):
        self._request_answer(self.result_window.pending_question)

    def _request_answer(self, question):
        if self.worker is not None or self.overlay is not None or self._jpeg is None:
            return
        if not self.cfg.get("api_key"):
            self.open_settings()
            return
        self.result_window.start_turn(question)
        self.worker = AnswerWorker(
            self.cfg["api_key"], self._prompt, self._jpeg, self.cfg.get("thinking", "high"),
            web_search=self.cfg.get("web_search", False), history=self.result_window.history,
            question=question, initial_instruction=self._initial_instruction, parent=self,
        )
        self.worker.chunk.connect(self.result_window.append_chunk)
        self.worker.reasoning.connect(self.result_window.append_reasoning)
        self.worker.searching.connect(self.result_window.show_searching)
        self.worker.finished.connect(self._answer_finished)
        self.worker.start()

    def _answer_finished(self):
        worker, self.worker = self.worker, None
        if worker.error:
            self.result_window.fail(worker.error)
        else:
            self.result_window.finish()
        worker.deleteLater()

    # ---------- 设置和退出 ----------

    def open_settings(self):
        if self.settings_dialog is not None:
            self.settings_dialog.raise_()
            self.settings_dialog.activateWindow()
            return
        self.settings_dialog = SettingsDialog(self.cfg)
        self.settings_dialog.saved.connect(self._on_settings_saved)
        self.settings_dialog.finished.connect(lambda _: setattr(self, "settings_dialog", None))
        self.settings_dialog.show()

    def _on_settings_saved(self, cfg):
        self.cfg = cfg
        self.snip_action.setText("截图提问（%s）" % cfg["hotkey"])
        self.register_hotkey()

    def quit(self):
        if self.worker is not None:
            self.tray.showMessage("截图解题", "请等当前请求完成后再退出。",
                                  QSystemTrayIcon.Information, 3000)
            return
        if self.overlay is not None:
            self.overlay.close()
        keyboard.unhook_all()
        self.qt_app.quit()


def _self_test():
    """验证打包后的 Qt、公式字体和语音依赖，无需密钥或联网。"""
    import os

    os.environ["QT_QPA_PLATFORM"] = "offscreen"
    app = QApplication([sys.argv[0]])
    window = ResultWindow()
    window.begin("启动自检")
    window.start_turn(None)
    window.append_chunk(r"公式测试：\(\frac{1}{2}\)")
    window.finish()
    app.processEvents()
    has_formula = "formula:/" in window.browser.document().toMarkdown()
    silent_wav = speech_wav(Recording(bytes(32000), 16000, 1, "h"))
    return 0 if has_formula and silent_wav is None else 1


def main():
    if sys.argv[1:] == ["--self-test"]:
        sys.exit(_self_test())
    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # 关掉所有窗口后仍驻留托盘
    app.setWindowIcon(make_tray_icon())   # 所有窗口统一图标，含标题栏左上角
    gui = App(app)
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
