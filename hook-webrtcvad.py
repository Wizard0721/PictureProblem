"""PyInstaller 使用带 Windows 预编译版本的 WebRTC VAD 包元数据。"""
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
