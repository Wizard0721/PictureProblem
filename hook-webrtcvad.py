"""为 PyInstaller 收录 webrtcvad-wheels 的包元数据，以便人声检测模块加载。"""
from PyInstaller.utils.hooks import copy_metadata

datas = copy_metadata("webrtcvad-wheels")
