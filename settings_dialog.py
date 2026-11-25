"""设置密钥和快捷键，切换联网搜索、语音输入、思考模式及自定义处理模式。"""
from uuid import uuid4

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QVBoxLayout,
)

import autostart
import config


class SettingsDialog(QDialog):
    saved = Signal(dict)

    def __init__(self, cfg, parent=None):
        super().__init__(parent)
        self.setWindowTitle("设置")
        self.setMinimumWidth(480)
        self._custom_modes = {mode["id"]: dict(mode) for mode in cfg.get("custom_modes", [])}
        self._editing_mode = None

        # API 密钥（默认打码显示，可勾选查看）
        self.key_edit = QLineEdit(cfg.get("api_key", ""))
        self.key_edit.setEchoMode(QLineEdit.Password)
        self.show_key = QCheckBox("显示密钥")
        self.show_key.toggled.connect(self._toggle_echo)

        self.hotkey_edit = QLineEdit(cfg.get("hotkey", "alt+q"))
        self.hotkey_edit.setPlaceholderText("例如 alt+q 或 ctrl+alt+s")

        self.style_combo = QComboBox()
        for mode_id, name in config.BUILTIN_MODES.items():
            self.style_combo.addItem(name, mode_id)
        for mode in self._custom_modes.values():
            self.style_combo.addItem(mode["name"], mode["id"])
        current = cfg.get("style", "explain")
        index = self.style_combo.findData(current)
        if index >= 0:
            self.style_combo.setCurrentIndex(index)

        self.new_mode = QPushButton("新建…")
        self.new_mode.clicked.connect(self._add_mode)
        mode_row = QHBoxLayout()
        mode_row.addWidget(self.style_combo, 1)
        mode_row.addWidget(self.new_mode)

        self.mode_name = QLineEdit()
        self.mode_name.setMaxLength(32)
        self.mode_name.setPlaceholderText("例如：只给解题提示")
        self.mode_prompt = QPlainTextEdit()
        self.mode_prompt.setPlaceholderText("例如：先指出考点，再给一个提示，等我追问后再写出答案。")
        self.mode_prompt.setMinimumHeight(104)
        self.delete_mode = QPushButton("删除此模式")
        self.delete_mode.clicked.connect(self._delete_mode)
        self.mode_name.textChanged.connect(self._update_mode)
        self.mode_prompt.textChanged.connect(self._update_mode)
        self.style_combo.currentIndexChanged.connect(self._select_mode)
        self.delete_row = QHBoxLayout()
        self.delete_row.addWidget(self.delete_mode)
        self.delete_row.addStretch(1)

        self.web_search_check = QCheckBox("允许 AI 按需联网搜索")
        self.web_search_check.setChecked(bool(cfg.get("web_search", False)))
        web_note = QLabel("可用于截图和追问，搜索费用单独计算。")
        web_note.setWordWrap(True)

        self.voice_check = QCheckBox("框选期间接收语音要求")
        self.voice_check.setChecked(bool(cfg.get("voice_input", False)))
        voice_note = QLabel("确认截图后，检测到人声的录音会发给 DeepSeek 转写，按时长计费。")
        voice_note.setWordWrap(True)

        self.thinking_combo = QComboBox()
        self.thinking_combo.addItem("关闭思考（最快、最省钱）", "off")
        self.thinking_combo.addItem("标准思考（推荐）", "high")
        self.thinking_combo.addItem("最大强度（更准，但更慢）", "max")
        current = cfg.get("thinking", "high")
        index = self.thinking_combo.findData(current)
        if index >= 0:
            self.thinking_combo.setCurrentIndex(index)

        # 开机自启勾选框：初始状态以系统启动项里的实际登记为准
        self.autostart_check = QCheckBox("开机自动启动")
        self.autostart_check.setChecked(autostart.is_enabled())
        self.autostart_check.setToolTip(
            "勾选后，电脑开机进入桌面时会自动运行本程序（最小化到右下角托盘）。\n"
            "也可以随时在任务管理器的“启动应用”里找到“截图解题”来开关。"
        )

        self.form = QFormLayout()
        self.form.addRow("DeepSeek 密钥：", self.key_edit)
        self.form.addRow("", self.show_key)
        self.form.addRow("截图快捷键：", self.hotkey_edit)
        self.form.addRow("截图语音输入：", self.voice_check)
        self.form.addRow("", voice_note)
        self.form.addRow("联网搜索：", self.web_search_check)
        self.form.addRow("", web_note)
        self.form.addRow("处理模式：", mode_row)
        self.form.addRow("模式名称：", self.mode_name)
        self.form.addRow("提示词：", self.mode_prompt)
        self.form.addRow("", self.delete_row)
        self.form.addRow("思考模式：", self.thinking_combo)
        self.form.addRow("", self.autostart_check)

        save_btn = QPushButton("保存")
        cancel_btn = QPushButton("取消")
        save_btn.clicked.connect(self._save)
        cancel_btn.clicked.connect(self.reject)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        btn_row.addWidget(save_btn)
        btn_row.addWidget(cancel_btn)

        layout = QVBoxLayout(self)
        layout.addLayout(self.form)
        layout.addLayout(btn_row)
        self._select_mode()

    def _toggle_echo(self, checked):
        self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _select_mode(self):
        mode_id = self.style_combo.currentData()
        mode = self._custom_modes.get(mode_id)
        self._editing_mode = None
        for row in (self.mode_name, self.mode_prompt, self.delete_row):
            self.form.setRowVisible(row, mode is not None)
        if mode is not None:
            self.mode_name.setText(mode["name"])
            self.mode_prompt.setPlainText(mode["prompt"])
            self._editing_mode = mode_id

    def _update_mode(self):
        if self._editing_mode is None:
            return
        mode = self._custom_modes[self._editing_mode]
        mode["name"] = self.mode_name.text()
        mode["prompt"] = self.mode_prompt.toPlainText()
        self.style_combo.setItemText(self.style_combo.currentIndex(),
                                     mode["name"].strip() or "未命名模式")

    def _add_mode(self):
        mode_id = f"custom:{uuid4().hex}"
        self._custom_modes[mode_id] = {"id": mode_id, "name": "", "prompt": ""}
        self.style_combo.addItem("未命名模式", mode_id)
        self.style_combo.setCurrentIndex(self.style_combo.count() - 1)
        self.mode_name.setFocus()

    def _delete_mode(self):
        if self._editing_mode is None:
            return
        index = self.style_combo.currentIndex()
        del self._custom_modes[self._editing_mode]
        self.style_combo.setCurrentIndex(0)
        self.style_combo.removeItem(index)

    def _save(self):
        key = self.key_edit.text().strip()
        hotkey = self.hotkey_edit.text().strip().lower() or "alt+q"
        modes = []
        names = {name.casefold() for name in config.BUILTIN_MODES.values()}
        for mode_id, draft in self._custom_modes.items():
            name, prompt = draft["name"].strip(), draft["prompt"].strip()
            if not name or not prompt or name.casefold() in names:
                self.style_combo.setCurrentIndex(self.style_combo.findData(mode_id))
                if not name or name.casefold() in names:
                    self.mode_name.setFocus()
                else:
                    self.mode_prompt.setFocus()
                QMessageBox.warning(self, "请检查处理模式", "每个自定义模式都需要一个不重复的名称和提示词。")
                return
            modes.append({"id": mode_id, "name": name, "prompt": prompt})
            names.add(name.casefold())

        # 开机自启：只在勾选状态和系统里的实际登记不一致时才动手改
        want_autostart = self.autostart_check.isChecked()
        try:
            if want_autostart != autostart.is_enabled():
                autostart.set_enabled(want_autostart)
        except OSError as e:
            QMessageBox.warning(
                self, "提示",
                "开机自启设置失败，其他设置仍会保存。\n错误信息：%s" % e,
            )

        # 在现有配置上更新，避免弄丢其他设置项（如字体大小）
        cfg = config.load()
        cfg.update({
            "api_key": key,
            "hotkey": hotkey,
            "style": self.style_combo.currentData(),
            "web_search": self.web_search_check.isChecked(),
            "voice_input": self.voice_check.isChecked(),
            "custom_modes": modes,
            "thinking": self.thinking_combo.currentData(),
            # 以登记后的实际结果为准，避免"保存了但没生效"的假状态
            "autostart": autostart.is_enabled(),
        })
        try:
            config.save(cfg)
        except OSError:
            QMessageBox.warning(self, "设置未保存", "无法写入配置文件，请检查程序目录的写入权限。")
            return
        self.saved.emit(cfg)
        self.accept()
