"""显示流式思考过程、正式回答及本题要求，并提供追问、重试和复制操作。"""
from dataclasses import dataclass
import re

from PySide6.QtCore import QEvent, QTimer, Qt, Signal
from PySide6.QtGui import (
    QColor,
    QDesktopServices,
    QGuiApplication,
    QPalette,
    QTextBlockFormat,
    QTextCharFormat,
    QTextCursor,
    QTextDocument,
    QTextDocumentFragment,
)
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPlainTextEdit,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

import config
from math_render import set_math_markdown


@dataclass(frozen=True)
class Turn:
    question: str | None
    answer: str
    reasoning: str


class AnswerBrowser(QTextBrowser):
    def loadResource(self, kind, url):
        # 公式图像由文档提供；回答中的其它图片不触发文件或网络读取。
        return None


class QuestionEdit(QPlainTextEdit):
    submit = Signal()

    def keyPressEvent(self, event):
        if (event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and event.modifiers() in (Qt.KeyboardModifier.NoModifier,
                                          Qt.KeyboardModifier.KeypadModifier)):
            self.submit.emit()
            event.accept()
        else:
            super().keyPressEvent(event)


class ResultWindow(QWidget):
    send_requested = Signal(str)
    instruction_requested = Signal(str)
    retry_requested = Signal()
    MIN_FONT = 10
    MAX_FONT = 28

    def __init__(self):
        super().__init__()
        self.setWindowTitle("截图解题")
        self.resize(560, 620)
        self.setMinimumSize(380, 320)
        self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        self._font_size = int(config.load().get("font_size", 12))
        self._turns = []
        self._text = ""
        self._reasoning = ""
        self._busy = False
        self._await_instruction = False
        self._instruction = ""
        self._instruction_heading = ""
        self.pending_question = None

        self.status = QLabel()
        self.status.setWordWrap(True)
        self.status.setTextFormat(Qt.TextFormat.PlainText)
        self.browser = AnswerBrowser()
        self.browser.setOpenLinks(False)
        self.browser.anchorClicked.connect(self._open_link)
        self.browser.setPlaceholderText("AI 回答会显示在这里。")
        self._apply_font()

        self.copy_btn = QPushButton("复制对话")
        self.close_btn = QPushButton("关闭")
        self.copy_btn.clicked.connect(self._copy)
        self.close_btn.clicked.connect(self.close)

        self.smaller_btn = QPushButton("A－")
        self.bigger_btn = QPushButton("A＋")
        self.smaller_btn.setToolTip("把回答文字调小一号")
        self.bigger_btn.setToolTip("把回答文字调大一号")
        self.smaller_btn.clicked.connect(lambda: self._change_font(-1))
        self.bigger_btn.clicked.connect(lambda: self._change_font(1))

        btn_row = QHBoxLayout()
        btn_row.addWidget(self.smaller_btn)
        btn_row.addWidget(self.bigger_btn)
        btn_row.addStretch(1)
        btn_row.addWidget(self.copy_btn)
        btn_row.addWidget(self.close_btn)

        self.composer = QuestionEdit()
        self.composer.setAccessibleName("追问内容")
        self.composer.setPlaceholderText("输入追问，Enter 发送，Shift+Enter 换行")
        self.composer.setTabChangesFocus(True)
        self.composer.setFixedHeight(68)
        self.composer.textChanged.connect(self._sync_controls)
        self.composer.submit.connect(self._submit)
        self.send_btn = QPushButton("发送")
        self.send_btn.clicked.connect(self._submit)
        self.retry_btn = QPushButton("重试")
        self.retry_btn.clicked.connect(self.retry_requested)
        self.retry_btn.hide()
        self.skip_voice_btn = QPushButton("仅用截图继续")
        self.skip_voice_btn.clicked.connect(lambda: self.instruction_requested.emit(""))
        self.skip_voice_btn.hide()

        composer_actions = QVBoxLayout()
        composer_actions.addWidget(self.send_btn)
        composer_actions.addWidget(self.retry_btn)
        composer_actions.addWidget(self.skip_voice_btn)
        composer_actions.addStretch(1)
        composer_row = QHBoxLayout()
        composer_row.addWidget(self.composer, 1)
        composer_row.addLayout(composer_actions)

        layout = QVBoxLayout(self)
        layout.addWidget(self.status)
        layout.addWidget(self.browser, 1)
        layout.addLayout(composer_row)
        layout.addLayout(btn_row)

        self._render_timer = QTimer(self)
        self._render_timer.setSingleShot(True)
        self._render_timer.setInterval(60)
        self._render_timer.timeout.connect(self._render)
        self.browser.viewport().installEventFilter(self)
        self._sync_controls()

    @property
    def history(self):
        return tuple((turn.question, turn.answer) for turn in self._turns)

    def _apply_font(self):
        font = self.browser.font()
        font.setPointSize(self._font_size)
        self.browser.setFont(font)
        self.browser.document().setDefaultFont(font)

    def _change_font(self, delta):
        new_size = max(self.MIN_FONT, min(self.MAX_FONT, self._font_size + delta))
        if new_size == self._font_size:
            return
        self._font_size = new_size
        self._apply_font()
        self._render()
        cfg = config.load()
        cfg["font_size"] = new_size
        config.save(cfg)

    def eventFilter(self, watched, event):
        if (watched is self.browser.viewport()
                and event.type() == QEvent.Type.Resize):
            self._schedule_render()
        return super().eventFilter(watched, event)

    def begin(self, mode_name):
        self.setWindowTitle(f"截图解题 · {mode_name}")
        self._turns.clear()
        self._text = ""
        self._reasoning = ""
        self._busy = False
        self.pending_question = None
        self._instruction = ""
        self._instruction_heading = ""
        self._set_instruction_input(False)
        self.composer.clear()
        self.retry_btn.hide()
        self._render()

    def reveal(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def start_turn(self, question):
        self._busy = True
        self.pending_question = question
        self._text = ""
        self._reasoning = ""
        if self._await_instruction:
            self._set_instruction_input(False)
            self.composer.clear()
        if question is not None and self.composer.toPlainText().strip() == question:
            self.composer.clear()
        self.retry_btn.hide()
        self.status.setText("正在分析截图…" if question is None else "正在处理追问…")
        self._sync_controls()
        self._render(force_bottom=True)

    def show_transcribing(self):
        self._busy = True
        self.status.setText("正在识别语音…")
        self._sync_controls()

    def show_voice_error(self, message):
        self._busy = False
        self.status.setText(f"{message} 截图已保留。")
        self._set_instruction_input(True)
        self._sync_controls()
        self.composer.setFocus()

    def set_initial_instruction(self, text, *, from_voice=False):
        self._instruction = text
        self._instruction_heading = "本题语音要求" if from_voice else "本题要求"

    def _set_instruction_input(self, enabled):
        self._await_instruction = enabled
        self.composer.setAccessibleName("本题要求" if enabled else "追问内容")
        self.composer.setPlaceholderText(
            "手动输入本题要求，Enter 发送" if enabled else "输入追问，Enter 发送，Shift+Enter 换行"
        )
        self.skip_voice_btn.setVisible(enabled)

    def append_reasoning(self, piece):
        if not self._reasoning and not self._text:
            self.status.setText("正在思考…")
        self._reasoning += piece
        if not self._text:
            self.copy_btn.setEnabled(True)
        self._schedule_render()

    def show_searching(self):
        self.status.setText("正在判断并查找相关资料…")

    def append_chunk(self, piece):
        if not self._text:
            self.status.setText("正在回答…")
        self._text += piece
        self.copy_btn.setEnabled(True)
        self._schedule_render()

    def finish(self):
        self._turns.append(Turn(self.pending_question, self._text, self._reasoning))
        self._busy = False
        self.pending_question = None
        self._text = ""
        self._reasoning = ""
        self.status.setText("回答完成，可以继续追问。")
        self._sync_controls()
        self._render()

    def fail(self, message):
        self._busy = False
        self.status.setText(message)
        self.retry_btn.show()
        self._sync_controls()
        self._render()

    def _sync_controls(self):
        can_follow = bool(self._turns)
        can_compose = can_follow or self._await_instruction
        self.composer.setEnabled(can_compose)
        self.send_btn.setEnabled(can_compose and not self._busy and bool(self.composer.toPlainText().strip()))
        self.copy_btn.setEnabled(can_follow or bool(self._text or self._reasoning or self._instruction))

    def _submit(self):
        if self.send_btn.isEnabled():
            signal = self.instruction_requested if self._await_instruction else self.send_requested
            signal.emit(self.composer.toPlainText().strip())

    def _schedule_render(self):
        if not self._render_timer.isActive():
            self._render_timer.start()

    def _entries(self):
        yield from self._turns
        if self.pending_question is not None or self._text or self._reasoning:
            yield Turn(self.pending_question, self._text, self._reasoning)

    def _sections(self):
        if self._instruction:
            yield self._instruction_heading, self._plain_markdown(self._instruction), False
        for turn in self._entries():
            if turn.question is not None:
                yield "你的追问", self._plain_markdown(turn.question), False
            if turn.reasoning.strip():
                yield "思考过程", turn.reasoning, True
            if turn.answer:
                yield "AI 回答", turn.answer, False

    def _render(self, force_bottom=False):
        self._render_timer.stop()
        bar = self.browser.verticalScrollBar()
        position = bar.value()
        at_bottom = bar.maximum() - position < 24
        document = self.browser.document()
        document.clear()
        cursor = QTextCursor(document)
        pixels = round(self._font_size * self.browser.logicalDpiY() / 72)
        color = self.browser.palette().color(QPalette.ColorRole.Text).name()
        max_width = max(80, self.browser.viewport().width() - 2 * document.documentMargin() - 16)
        thinking_style = self._reasoning_format()
        # 独立解析各段，避免未闭合的 Markdown 影响后面的回答。
        for title, text, is_reasoning in self._sections():
            section = QTextDocument()
            section.setDefaultFont(document.defaultFont())
            heading = QTextBlockFormat()
            heading.setHeadingLevel(4)
            heading.setTopMargin(12 if not document.isEmpty() else 0)
            heading.setBottomMargin(6)
            if not document.isEmpty():
                cursor.insertBlock(heading, QTextCharFormat())
            else:
                cursor.setBlockFormat(heading)
            formula_color = thinking_style.foreground().color().name() if is_reasoning else color
            set_math_markdown(section, f"#### {title}\n\n{text}", pixels, formula_color,
                              max_width, resource_document=document)
            if is_reasoning:
                first_body_block = section.begin().next()
                if first_body_block.isValid():
                    style = QTextCursor(first_body_block)
                    style.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
                    style.mergeCharFormat(thinking_style)
            cursor.insertFragment(QTextDocumentFragment(section))
        bar.setValue(bar.maximum() if force_bottom or at_bottom else position)

    def _reasoning_format(self):
        palette = self.browser.palette()
        text = palette.color(QPalette.ColorRole.Text)
        base = palette.color(QPalette.ColorRole.Base)
        dimmed = QColor.fromRgbF(*(a * 0.84 + b * 0.16
                                   for a, b in zip(text.getRgbF()[:3], base.getRgbF()[:3])))
        fmt = QTextCharFormat()
        fmt.setFontFamilies(["KaiTi", "SimSun", "Cambria", "Georgia"])
        fmt.setForeground(dimmed)
        return fmt

    def _copy(self):
        parts = []
        if self._instruction:
            parts.append(f"{self._instruction_heading}：\n{self._instruction}")
        for turn in self._entries():
            if turn.question is not None:
                parts.append("你的追问：\n" + turn.question)
            if turn.reasoning.strip():
                parts.append("思考过程：\n" + turn.reasoning)
            if turn.answer:
                parts.append(("AI 回答：\n" if parts else "") + turn.answer)
        if parts:
            QGuiApplication.clipboard().setText("\n\n".join(parts))

    @staticmethod
    def _plain_markdown(text):
        return re.sub(r"([\\\x60~*_{}\[\]()<>#+\-.!|$])", r"\\\1", text).replace("\n", "  \n")

    @staticmethod
    def _open_link(url):
        if url.scheme() in ("https", "http") and url.host():
            QDesktopServices.openUrl(url)
