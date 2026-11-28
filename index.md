# 文件索引

下表按文件说明项目各部分的职责，包括可直接运行的 Windows EXE 和源码所需的依赖。

## 仓库根目录

| 文件 | 用途 |
| --- | --- |
| [README.md](README.md) | 介绍截图解题，说明如何安装、配置 API 密钥、从源码运行和打包。 |
| [index.md](index.md) | 逐项说明仓库文件及本机生成的文件。 |
| [.gitignore](.gitignore) | 指定 Git 应忽略的本机配置、缓存、快捷方式和构建产物。 |
| [main.py](main.py) | 程序入口。启动系统托盘，连接截图快捷键，并调度框选、语音转写和 AI 回答。 |
| [hotkey.py](hotkey.py) | 通过 Windows 原生接口注册、切换和释放全局截图快捷键。 |
| [overlay.py](overlay.py) | 显示全屏框选层，按显示器缩放比例裁剪截图，并提示录音状态。 |
| [voice_input.py](voice_input.py) | 在框选期间录制麦克风音频，在本机检测人声，并把有语音的片段转换为 WAV。 |
| [api.py](api.py) | 调用 DeepSeek 的语音转写、联网搜索和图片问答接口，构建多轮对话请求并读取流式返回。 |
| [result_window.py](result_window.py) | 显示语音要求、思考过程和正式回答，提供追问、重试与复制对话操作。 |
| [math_render.py](math_render.py) | 解析回答中的 Markdown，在 Qt 文档里排版行内和独立的 LaTeX 公式。 |
| [settings_dialog.py](settings_dialog.py) | 提供密钥、快捷键、联网搜索、语音输入、思考模式和自定义提示词的设置界面。 |
| [config.py](config.py) | 定义默认设置，读写程序旁边的本机配置。 |
| [autostart.py](autostart.py) | 读取或修改截图解题的 Windows 开机启动项。 |
| [requirements.txt](requirements.txt) | 列出运行源码需要安装的 Python 依赖。 |
| [PictureProblem-Windows-x64.exe](PictureProblem-Windows-x64.exe) | 内置运行库的 Windows x64 程序，可直接下载运行。 |
| [截图解题.spec](截图解题.spec) | 指定 PyInstaller 的入口、资源和依赖，用于构建无需安装 Python 的 Windows EXE。 |
| [hook-webrtcvad.py](hook-webrtcvad.py) | 让 PyInstaller 收录 WebRTC 人声检测库运行所需的包元数据。 |
| [icon.ico](icon.ico) | Windows 可执行文件使用的程序图标。 |

## 本机文件

| 文件 | 用途 |
| --- | --- |
| `截图解题.exe` | 在本机打包生成的 Windows 程序；仓库里的下载版文件名为 `PictureProblem-Windows-x64.exe`。 |
| `config.json` | 用户保存设置后生成的本机配置，含自己的 DeepSeek API 密钥和偏好，不上传。 |
| `截图解题.lnk` | 指向本机程序路径的 Windows 快捷方式，不上传。 |
| `截图解题.exe.previous` | 更新程序时留下的旧版备份，可在退出旧版后删除，不上传。 |
| `__pycache__/` | Python 运行源码时生成的字节码缓存，不上传。 |
| `build/` | PyInstaller 打包时生成的临时文件，不上传。 |
| `dist/` | PyInstaller 默认写入成品 EXE 的目录。 |
