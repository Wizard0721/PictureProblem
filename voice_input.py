"""在框选期间采集麦克风音频，检测人声后在内存中封装 WAV。"""
from array import array
from collections import deque
from dataclasses import dataclass
from io import BytesIO
import sys
import wave

import webrtcvad
from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtMultimedia import QAudio, QAudioFormat, QAudioSource, QMediaDevices


MAX_SECONDS = 30
_RATE = 16000
_FRAME_BYTES = _RATE * 20 // 1000 * 2
_FORMATS = {
    QAudioFormat.SampleFormat.UInt8: "B",
    QAudioFormat.SampleFormat.Int16: "h",
    QAudioFormat.SampleFormat.Int32: "i",
    QAudioFormat.SampleFormat.Float: "f",
}


class CaptureError(Exception):
    pass


@dataclass(frozen=True)
class Recording:
    pcm: bytes
    rate: int
    channels: int
    sample_type: str


def _capture_format(device):
    pcm = QAudioFormat()
    pcm.setChannelCount(1)
    pcm.setSampleFormat(QAudioFormat.SampleFormat.Int16)
    for rate in (_RATE, 48000):
        pcm.setSampleRate(rate)
        if device.isFormatSupported(pcm):
            return pcm
    return device.preferredFormat()


class MicrophoneCapture(QObject):
    """仅在框选期打开设备；采样数据最多保留 30 秒。"""
    status_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._source = None
        self._device = None
        self._format = None
        self._limit = 0
        self._pcm = bytearray()
        self._error = ""
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._time_limit)

    def start(self):
        device = QMediaDevices.defaultAudioInput()
        if device.isNull():
            self._fail("找不到麦克风。请连接麦克风或手动输入本次要求。")
            return
        fmt = _capture_format(device)
        if not fmt.isValid() or fmt.sampleFormat() not in _FORMATS:
            self._fail("当前麦克风的录音格式不可用。请手动输入本次要求。")
            return
        self._format = fmt
        self._limit = fmt.bytesForDuration(MAX_SECONDS * 1_000_000)
        self._source = QAudioSource(device, fmt, self)
        self._source.setBufferSize(fmt.bytesForDuration(60_000))
        self._source.stateChanged.connect(self._state_changed)
        self._device = self._source.start()
        if self._device is None or self._source.error() != QAudio.Error.NoError:
            self._fail("无法开始录音。请检查 Windows 的麦克风权限或手动输入本次要求。")
            return
        self._device.readyRead.connect(self._read)
        self._read()
        self._timer.start(MAX_SECONDS * 1000)
        self.status_changed.emit("正在听 · 可以先说，再框选")

    def _read(self):
        if self._device is not None:
            data = bytes(self._device.readAll())
            self._pcm.extend(data[:max(0, self._limit - len(self._pcm))])

    def _state_changed(self, state):
        if state == QAudio.State.StoppedState and self._device is not None:
            if self._source.error() != QAudio.Error.NoError:
                self._fail("麦克风录音中断。请检查设备或手动输入本次要求。")

    def _fail(self, message):
        self._error = message
        self.discard()
        self.status_changed.emit("麦克风不可用 · 可在截图后输入要求")

    def _time_limit(self):
        self._stop(keep=True)
        self.status_changed.emit(f"录音已满 {MAX_SECONDS} 秒 · 框选后提交")

    def _stop(self, *, keep):
        self._timer.stop()
        if keep:
            self._read()
        self._device = None
        source, self._source = self._source, None
        if source is not None:
            source.stop()
            source.deleteLater()

    def finish(self):
        """停止采集，交出完整帧；录音始终不会写入文件。"""
        self._stop(keep=True)
        if self._error:
            raise CaptureError(self._error)
        if not self._pcm:
            return None
        fmt = self._format
        result = Recording(bytes(self._pcm), fmt.sampleRate(), fmt.channelCount(),
                           _FORMATS[fmt.sampleFormat()])
        self._pcm.clear()
        return result

    def discard(self):
        self._stop(keep=False)
        self._pcm.clear()


def _mono_16k(recording):
    samples = array(recording.sample_type)
    frame_size = samples.itemsize * recording.channels
    samples.frombytes(recording.pcm[:len(recording.pcm) // frame_size * frame_size])
    if recording.rate == _RATE and recording.channels == 1 and recording.sample_type == "h":
        mono = samples
    else:
        offset, gain = {"B": (128, 256), "h": (0, 1), "i": (0, 1 / 65536),
                        "f": (0, 32768)}[recording.sample_type]
        mono = array("h")
        count = len(samples) // recording.channels * _RATE // recording.rate
        # 以目标采样区间求均值，兼容 44.1 kHz、双声道和浮点输入。
        step = recording.channels
        for i in range(count):
            start = i * recording.rate // _RATE
            end = max(start + 1, (i + 1) * recording.rate // _RATE)
            if step == 1:
                selected = samples[start:end]
            else:
                selected = samples[start * step:end * step]
            sample = (sum(selected) / len(selected) - offset) * gain
            mono.append(int(max(-32768, min(32767, sample))))
    if sys.byteorder == "big":
        mono.byteswap()
    return mono.tobytes()


def speech_wav(recording):
    """跳过静音和短促杂音；保留语音首尾附近的采样供转写。"""
    pcm = _mono_16k(recording)
    samples = array("h")
    samples.frombytes(pcm)
    if sys.byteorder == "big":
        samples.byteswap()
    frame_samples = _FRAME_BYTES // 2
    starts = range(0, len(samples) - frame_samples + 1, frame_samples)
    energy = [sum(value * value for value in samples[start:start + frame_samples])
              for start in starts]
    if len(energy) < 4:
        return None
    # WebRTC 会在短促声音后继续返回若干人声帧；同时检查当前帧的能量，
    # 避免一次点击或稳定底噪触发上传。
    floor = sorted(energy)[len(energy) // 5]
    minimum = max(48 ** 2 * frame_samples, floor * 3)
    vad = webrtcvad.Vad(2)
    window = deque(maxlen=8)
    first = last = None
    for index, power in enumerate(energy):
        start = index * _FRAME_BYTES
        if vad.is_speech(pcm[start:start + _FRAME_BYTES], _RATE) and power >= minimum:
            window.append(start)
        else:
            window.append(None)
        voiced = [position for position in window if position is not None]
        if len(voiced) >= 4:
            if first is None:
                first = voiced[0]
            last = voiced[-1]
    if first is None:
        return None
    padding = 10 * _FRAME_BYTES
    result = BytesIO()
    with wave.open(result, "wb") as output:
        output.setparams((1, 2, _RATE, 0, "NONE", "not compressed"))
        output.writeframes(pcm[max(0, first - padding):last + _FRAME_BYTES + padding])
    return result.getvalue()
