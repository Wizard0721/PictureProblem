"""显示全屏框选层，按比例裁剪截图，并提示录音状态。

工作方式：按下快捷键时先把整个屏幕拍成一张静态图，然后弹出一个全屏窗口把这张
静态图显示出来并压暗一层。用户在上面拖出一个方框，松开鼠标后按屏幕缩放比例把
方框换算成原始物理像素，从静态图里裁出对应区域，交给主程序去调用接口。

Qt 6 在 Windows 上默认开启了“按显示器感知缩放”（per-monitor DPI awareness），
窗口坐标是逻辑坐标，截屏图像是物理像素，两者的倍率就是 devicePixelRatio。
所有框选坐标乘以这个倍率就能精确对应到真实屏幕像素，因此在 100%、125%、150%
等任何显示缩放下都不会截偏。
"""
from PySide6.QtCore import QBuffer, QIODevice, QRect, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QWidget

from voice_input import CaptureError, MicrophoneCapture

MIN_SIZE = 10  # 小于这个尺寸的方框视为误触


def physical_rect(logical, dpr):
    """把窗口里的逻辑坐标方框换算成截屏图像里的物理像素方框。

    画方框（paintEvent）和真正裁剪（_finish_select）必须使用同一个换算，
    否则在 125%/150% 缩放下会出现“看到的框”和“裁出的图”差一两个像素。
    统一使用四舍五入，误差不超过半像素。
    """
    return QRect(
        round(logical.x() * dpr),
        round(logical.y() * dpr),
        max(1, round(logical.width() * dpr)),
        max(1, round(logical.height() * dpr)),
    )


class SnipOverlay(QWidget):
    selected = Signal(bytes, object, str)  # JPEG、录音（可空）、麦克风错误
    cancelled = Signal()

    def __init__(self, screen, *, voice_input=False):
        super().__init__(None, Qt.WindowStaysOnTopHint | Qt.FramelessWindowHint | Qt.Tool)
        self.setScreen(screen)
        self.setGeometry(screen.geometry())

        # 先抓屏再开窗，窗口里显示的是抓下来的静态画面
        self._pixmap = screen.grabWindow(0)
        # 缩放比例从抓到的图像里读取（Windows 实时报告的值）；
        # 万一读取失败，退回用屏幕参数里的比例，绝不能想当然按 100% 处理
        self._dpr = self._pixmap.devicePixelRatio()
        if self._dpr <= 0:
            self._dpr = screen.devicePixelRatio() or 1.0

        self._origin = None
        self._rect = QRect()
        self._submitted = False
        self._voice_status = ""
        self._mic = MicrophoneCapture(self) if voice_input else None
        if self._mic is not None:
            self._mic.status_changed.connect(self._set_voice_status)
        self.setCursor(Qt.CrossCursor)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.StrongFocus)

    def start(self):
        self.showFullScreen()
        self.activateWindow()
        self.setFocus()
        if self._mic is not None:
            self._mic.start()

    def _set_voice_status(self, message):
        self._voice_status = message
        self.update()

    # ---------- 绘制 ----------

    def paintEvent(self, event):
        p = QPainter(self)
        # 背景：整张静态画面 + 一层半透明黑
        p.drawPixmap(self.rect(), self._pixmap)
        p.fillRect(self.rect(), QColor(0, 0, 0, 110))

        if not self._rect.isNull():
            self._paint_selection(p)
        self._paint_status(p)

    def _paint_status(self, p):
        f_info = QFont()
        f_info.setPointSize(9)
        p.setFont(f_info)
        fm_info = QFontMetrics(f_info)
        info = self._voice_status or ("屏幕缩放 %d%%，已自动适配" % round(self._dpr * 100))
        listening = info.startswith("正在听")
        offset = 14 if listening else 0
        badge = QRect(12, 10, fm_info.horizontalAdvance(info) + 20 + offset, fm_info.height() + 8)
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(16, 20, 26, 230))
        p.drawRoundedRect(badge, 4, 4)
        if listening:
            p.setBrush(QColor(255, 117, 116))
            p.drawEllipse(badge.left() + 10, badge.center().y() - 3, 7, 7)
        p.setPen(QColor(247, 249, 252))
        p.drawText(badge.adjusted(10 + offset, 0, -10, 0), Qt.AlignLeft | Qt.AlignVCenter, info)

    def _paint_selection(self, p):
        r = self._rect
        # 方框内恢复原始亮度（从静态图里取出对应物理像素区域）
        src = physical_rect(r, self._dpr)
        p.drawPixmap(r, self._pixmap, src)

        # 边框：先画一圈深色描边，再画亮蓝色主框，深浅背景下都醒目
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor(0, 0, 0, 170), 1))
        p.drawRect(r.adjusted(-2, -2, 2, 2))
        p.setPen(QPen(QColor(0, 168, 255), 2))
        p.drawRect(r)

        # 四角画小方块手柄
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 168, 255))
        s = 8
        for cx, cy in ((r.left(), r.top()), (r.right(), r.top()),
                       (r.left(), r.bottom()), (r.right(), r.bottom())):
            p.drawRect(QRect(cx - s // 2, cy - s // 2, s, s))

        # 尺寸标签：深色底的圆角小条配白字，任何背景下都看得清
        f = QFont()
        f.setPointSize(10)
        p.setFont(f)
        fm = QFontMetrics(f)
        label = "%d x %d" % (r.width(), r.height())
        lw = fm.horizontalAdvance(label) + 16
        lh = fm.height() + 6
        lx = r.left()
        ly = r.top() - lh - 8
        if ly < 2:
            ly = r.bottom() + 8  # 框顶到屏幕上沿时，标签改放框下方
        p.setPen(Qt.NoPen)
        p.setBrush(QColor(0, 0, 0, 170))
        p.drawRoundedRect(QRect(lx, ly, lw, lh), 4, 4)
        p.setPen(QColor("white"))
        p.drawText(QRect(lx, ly, lw, lh), Qt.AlignCenter, label)

    # ---------- 鼠标和键盘 ----------

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._origin = event.position().toPoint()
            self._rect = QRect(self._origin, self._origin)
            self.update()
        elif event.button() == Qt.RightButton:
            self._finish_cancel()

    def mouseMoveEvent(self, event):
        if self._origin is not None:
            old = QRect(self._rect)
            self._rect = QRect(self._origin, event.position().toPoint()).normalized()
            # 只重绘新旧方框附近的区域，拖动更跟手；余量要盖住描边和标签
            self.update(old.united(self._rect).adjusted(-40, -40, 40, 40))

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self._origin is not None:
            if self._rect.width() < MIN_SIZE or self._rect.height() < MIN_SIZE:
                self._finish_cancel()
                return
            self._finish_select()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Escape:
            self._finish_cancel()

    # ---------- 收尾 ----------

    def _finish_cancel(self):
        self.close()

    def closeEvent(self, event):
        super().closeEvent(event)
        if not self._submitted:
            if self._mic is not None:
                self._mic.discard()
            self.cancelled.emit()

    def _finish_select(self):
        recording = None
        error = ""
        if self._mic is not None:
            try:
                recording = self._mic.finish()
            except CaptureError as exc:
                error = str(exc)
        pm_rect = physical_rect(self._rect, self._dpr)
        crop = self._pixmap.copy(pm_rect)

        buf = QBuffer()
        buf.open(QIODevice.WriteOnly)
        if not crop.save(buf, "JPEG", 88):
            self._finish_cancel()
            return
        self._submitted = True
        self.close()
        self.selected.emit(bytes(buf.data()), recording, error)
