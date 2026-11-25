"""在 Qt 文本文档里渲染 Markdown 与 LaTeX，无需浏览器。"""
from functools import lru_cache
from hashlib import sha256
import re

import ziafont
import ziamath
from PySide6.QtCore import QRectF, QUrl, Qt
from PySide6.QtGui import QImage, QPainter, QTextCursor, QTextDocument
from PySide6.QtSvg import QSvgRenderer


# Qt 的 SVG 渲染器需要直接的字形路径，而不是 SVG 2 的 symbol 引用。
ziafont.config.svg2 = False

_TOKENS = re.compile(
    r"(?P<fence>^[ \t]{0,3}(?P<markers>\x60{3,}|~{3,})[^\n]*\n"
    r"[\s\S]*?(?:^[ \t]{0,3}(?P=markers)[ \t]*(?=\n|$)|\Z))"
    r"|(?P<code>(?<!\x60)(?P<ticks>\x60+)(?!\x60)[^\n]*?(?<!\x60)(?P=ticks)(?!\x60))"
    r"|(?P<escaped>\\\\|\\\$)"
    r"|\\\[(?P<bracket>[\s\S]+?)\\\]"
    r"|(?<!\$)\$\$(?P<display>[\s\S]+?)\$\$(?!\$)"
    r"|\\\((?P<paren>[^\n]+?)\\\)"
    r"|(?<!\$)\$(?![\s$])(?P<inline>(?:\\.|[^\\$\n])+?)(?<!\s)\$(?![\d$])",
    re.MULTILINE,
)


@lru_cache(maxsize=128)
def _render_formula(latex, size, color, inline):
    if len(latex) > 4096:
        return None
    try:
        svg = ziamath.Latex(latex, size=size, color=color, inline=inline).svg()
        renderer = QSvgRenderer(svg.encode("utf-8"))
        bounds = renderer.viewBoxF()
        if not renderer.isValid() or bounds.width() <= 0 or bounds.height() <= 0:
            return None
        # 图像保留两倍清晰度，文档布局使用原始尺寸。
        width, height = bounds.width(), bounds.height()
        scale = min(2, 2048 / max(width, height), (524288 / (width * height)) ** 0.5)
        image = QImage(max(1, round(width * scale)), max(1, round(height * scale)),
                       QImage.Format.Format_ARGB32_Premultiplied)
        if image.isNull():
            return None
        image.fill(Qt.GlobalColor.transparent)
        painter = QPainter(image)
        try:
            renderer.render(painter, QRectF(image.rect()))
        finally:
            painter.end()
        return image, width, height
    except Exception:
        # 不完整或不支持的语法仍以原文显示。
        return None


def _literal_formula(tex):
    longest = max((len(run) for run in re.findall(r"\x60+", tex)), default=0)
    delimiters = chr(96) * (longest + 1)
    flat = " ".join(tex.split())
    return f"{delimiters} {flat} {delimiters}"


def set_math_markdown(document, markdown, pixels, color, max_width, *, resource_document=None):
    """把已闭合的公式放进 Qt 文档，正文仍由 Qt 处理 Markdown。"""
    formulas = {}

    def replace(match):
        syntax = next((key for key in ("bracket", "display", "paren", "inline")
                       if match[key] is not None), None)
        if syntax is None:
            return match[0]
        inline = syntax in ("paren", "inline")
        tex = match[syntax].strip()
        if not tex:
            return match[0]
        rendered = _render_formula(tex, pixels, color, inline)
        if rendered is None:
            replacement = _literal_formula(tex)
        else:
            name = "formula:/" + sha256(f"{inline}:{pixels}:{color}:{tex}".encode("utf-8")).hexdigest()
            formulas[name] = rendered
            replacement = f"![公式]({name})"
        return replacement if inline else f"\n\n{replacement}\n\n"

    markdown = _TOKENS.sub(replace, markdown)
    flags = (QTextDocument.MarkdownFeature.MarkdownDialectGitHub
             | QTextDocument.MarkdownFeature.MarkdownNoHTML)
    document.setMarkdown(markdown, flags)
    if not formulas:
        return
    for name, (image, _, _) in formulas.items():
        document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)
        if resource_document is not None:
            resource_document.addResource(QTextDocument.ResourceType.ImageResource, QUrl(name), image)

    images = []
    block = document.begin()
    while block.isValid():
        for iterator in block:
            part = iterator.fragment()
            fmt = part.charFormat()
            if fmt.isImageFormat() and fmt.toImageFormat().name() in formulas:
                images.append((part.position(), part.length(), fmt.toImageFormat()))
        block = block.next()

    cursor = QTextCursor(document)
    for position, length, fmt in images:
        _, width, height = formulas[fmt.name()]
        scale = min(1, max_width / width)
        fmt.setWidth(width * scale)
        fmt.setHeight(height * scale)
        cursor.setPosition(position)
        cursor.setPosition(position + length, QTextCursor.MoveMode.KeepAnchor)
        cursor.setCharFormat(fmt)
