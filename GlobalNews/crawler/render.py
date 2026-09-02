#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""HTML 渲染与按周存档：读 template.html 注入数据生成 news.html，并归档到 archive/。"""

import os
import json
import logging
from datetime import datetime
from typing import Dict, List

logger = logging.getLogger("crawler")

# ---------------------------------------------------------------------------
# 文件路径 — render.py 上两级目录即 GlobalNews/
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TEMPLATE_FILE = os.path.join(BASE_DIR, "template.html")
HTML_FILE = os.path.join(BASE_DIR, "news.html")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")

TODAY_STR = datetime.now().strftime("%Y-%m-%d")


# ===================================================================
# 生成 news.html
# ===================================================================
def generate_html(entries: List[Dict]) -> str:
    """
    从 template.html 读取模板，将全部数据注入，
    生成自包含的 news.html 阅读页面。失败时抛 RuntimeError（由入口捕获）。
    """
    # 读取模板文件
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            template = f.read()
    except (IOError, FileNotFoundError) as e:
        logger.error("读取模板文件 %s 失败: %s", TEMPLATE_FILE, e)
        raise RuntimeError(f"读取模板文件失败: {TEMPLATE_FILE}: {e}")

    json_str = json.dumps(entries, ensure_ascii=False)
    html_content = template.replace("__JSON_DATA_PLACEHOLDER__", json_str)

    try:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("HTML 已生成 → %s (%d 条)", HTML_FILE, len(entries))
    except IOError as e:
        logger.error("写入 %s 失败: %s", HTML_FILE, e)
        raise RuntimeError(f"写入 HTML 失败: {HTML_FILE}: {e}")

    return html_content


# ===================================================================
# 按周存档
# ===================================================================
def archive_html(html_content: str) -> None:
    """
    将当前生成的 HTML 内容按周存档到 archive/ 目录。
    文件名格式: news_YYYY_MM_DD.html
    """
    try:
        os.makedirs(ARCHIVE_DIR, exist_ok=True)
    except OSError as e:
        logger.error("创建 archive 目录失败: %s", e)
        return

    arch_name = f"news_{TODAY_STR.replace('-', '_')}.html"
    arch_path = os.path.join(ARCHIVE_DIR, arch_name)

    try:
        with open(arch_path, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("存档已保存 → %s", arch_path)
    except IOError as e:
        logger.error("写入存档 %s 失败: %s", arch_path, e)
