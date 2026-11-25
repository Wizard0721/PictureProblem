# 截图解题

截图解题是一个 Windows 托盘工具。按快捷键框选屏幕区域，程序调用 DeepSeek 识别截图并回答。回答支持 Markdown 和 LaTeX，可以在同一张截图下继续追问。

Windows x64 用户可直接运行发布的 EXE；从源码运行时需要安装 Python 依赖。

## 使用

1. 从 [Releases](https://github.com/Wizard0721/PictureProblem/releases) 下载 Windows 可执行文件，放在可写目录中运行。
2. 从托盘菜单打开「设置」，填入自己的 DeepSeek API 密钥。默认截图快捷键为 `Alt+Q`。
3. 用快捷键框选题目，等待回答。按 `Esc` 或右键可以取消截图。

设置中可以保存自己的处理模式和提示词，也可以分别启用联网搜索和截图语音输入。启用语音输入后，可在框选期间说出本题要求，说完再松开鼠标。启用思考模式后，回答窗口会单独显示 DeepSeek 返回的思考过程。

程序把截图和提问发送给 DeepSeek。开启语音输入并确认截图时，检测到人声的录音也会发给 DeepSeek 转写。API 密钥及设置存放在程序旁边的本机 `config.json`。

## 从源码运行和打包

在 Windows 上安装 Python 3.11，然后在项目目录运行：

```powershell
python -m pip install -r requirements.txt
python main.py
```

如需生成单文件 EXE：

```powershell
python -m pip install pyinstaller
python -m PyInstaller --noconfirm '截图解题.spec'
```

默认构建产物位于 `dist` 目录。项目文件见 [文件索引](index.md)。
