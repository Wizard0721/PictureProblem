"""本地配置的读取和保存。开发时存在代码目录，打包成 exe 后存在 exe 旁边。"""
import json
import os
import sys


def _base_dir():
    # 打包成单文件 exe 运行时，代码会被解压到临时目录，
    # 配置文件必须放在 exe 本体旁边才能持久保存
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_PATH = os.path.join(_base_dir(), "config.json")

DEFAULTS = {
    "api_key": "",
    "hotkey": "alt+q",
    "style": "explain",      # explain=讲解, answer=直接回答, fact_check=事实验证
    "thinking": "high",      # off=关闭思考, high=标准思考, max=最大强度
    "font_size": 12,
    "autostart": False,      # 开机自动启动
    "web_search": False,
    "voice_input": False,
    "custom_modes": [],
}

BUILTIN_MODES = {
    "explain": "一步步讲解",
    "answer": "直接给答案",
    "fact_check": "事实验证",
}


def load():
    cfg = dict(DEFAULTS)
    cfg["custom_modes"] = []
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f)
            if isinstance(stored, dict):
                cfg.update(stored)
                if "web_search" not in stored:
                    cfg["web_search"] = stored.get("style") == "fact_check"
        except (json.JSONDecodeError, OSError):
            pass
    return cfg


def save(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
