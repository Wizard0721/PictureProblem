# 截图解题

截图解题是一个 Windows 托盘工具。按快捷键框选屏幕区域，程序调用 DeepSeek 识别截图并回答。回答支持 Markdown 和 LaTeX，可以在同一张截图下继续追问。

**[直接下载 Windows x64 EXE](https://github.com/Wizard0721/PictureProblem/raw/refs/heads/main/PictureProblem-Windows-x64.exe)**。安装 Python 只在从源码运行时需要。

## 使用

1. 下载仓库根目录里的 `PictureProblem-Windows-x64.exe`，放在可写目录中运行。EXE 已内置运行库，无需单独安装 Python 或下载 DLL。
2. 从托盘菜单打开「设置」，填入自己的 DeepSeek API 密钥。默认截图快捷键为 `Alt+Q`。
3. 用快捷键框选题目，等待回答。按 `Esc` 或右键可以取消截图。

截图快捷键可以在「设置」中修改，例如 `Ctrl+Alt+S` 或 `F8`。如果某个组合键已被 Windows 或其他程序占用，请换一个。也可以直接从托盘菜单选择「截图提问」。

需要一次下载源码和 EXE，可以在仓库首页选择 **Code → Download ZIP**。历史版本见 [Releases](https://github.com/Wizard0721/PictureProblem/releases)。

设置中可以保存自己的处理模式和提示词，也可以分别启用联网搜索和截图语音输入。启用语音输入后，按截图快捷键，看到「正在听」就可以说出本题要求，说完再松开鼠标。识别出的文字会显示为「本题语音要求」。如需切换麦克风，请到 Windows「设置 → 系统 → 声音 → 输入」选择默认输入设备。启用思考模式后，回答窗口会单独显示 DeepSeek 返回的思考过程。

正式答案会突出结论，用小标题分节，并让步骤、正文和公式各有合适的间距。思考过程继续使用楷体。

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
