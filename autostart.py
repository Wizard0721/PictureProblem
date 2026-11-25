"""通过 Windows 启动项登记或取消程序的开机自启。

原理说明：Windows 给每个用户都留了一份"开机要启动哪些软件"的登记表
（注册表 HKEY_CURRENT_USER 下的 Run 项）。把本程序的路径写进去，
开机后 Windows 就会自动运行它；把这条登记删掉，就不再自动运行。
只写自己用户名下的登记，不需要管理员权限。
"""
import os
import sys

import winreg

# 登记所在位置和登记用的名字（任务管理器的"启动应用"里显示的就是这个名字）
_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_ENTRY_NAME = "截图解题"


def _command():
    """返回开机时 Windows 要执行的那条启动命令。"""
    if getattr(sys, "frozen", False):
        # 打包成 exe 后，启动的就是 exe 本体（引号防止路径里有空格时被拆开）
        return '"%s"' % sys.executable
    # 开发阶段还没打包：用 pythonw.exe（不带黑色命令行窗口）运行 main.py
    main_py = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    pythonw = os.path.join(os.path.dirname(sys.executable), "pythonw.exe")
    if not os.path.exists(pythonw):
        pythonw = sys.executable
    return '"%s" "%s"' % (pythonw, main_py)


def is_enabled():
    """当前是否已经登记了开机自启。"""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _ENTRY_NAME)
            return True
    except OSError:
        return False


def set_enabled(enable):
    """登记（True）或取消（False）开机自启。操作失败会抛出 OSError。"""
    if enable:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            winreg.SetValueEx(key, _ENTRY_NAME, 0, winreg.REG_SZ, _command())
    else:
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
                winreg.DeleteValue(key, _ENTRY_NAME)
        except FileNotFoundError:
            pass  # 本来就没登记过，取消时不算出错
