#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
数据合并 + 核心流水线。

merge_data: 读 news_data.json → URL 去重 → 标题相似标记 → 合并 →
            published 降序 → 写回（v2 起全量保留历史，无月度清理、无栏目上限）。
run_crawl:  抓取 RSS → 详情富化 → 附件归档 → 合并去重 → 渲染存档。

日志配置（含 Windows 控制台 UTF-8 重定向）留在各入口文件，本模块只取 logger。
"""

import os
import json
import logging
from datetime import datetime
from difflib import SequenceMatcher
from typing import Dict, List

from crawler import fetch, detail, attachments
from crawler import render

logger = logging.getLogger("crawler")

# ---------------------------------------------------------------------------
# 文件路径 — pipeline.py 上两级目录即 GlobalNews/
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_FILE = os.path.join(BASE_DIR, "news_data.json")

TODAY_STR = datetime.now().strftime("%Y-%m-%d")


# ===================================================================
# 标题相似度检测（用于辅助去重）
# ===================================================================
def titles_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """两个标题的相似度 >= threshold 时返回 True"""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= threshold


# ===================================================================
# 与历史数据合并去重（全量保留）
# ===================================================================
def merge_data(new_entries: List[Dict]) -> List[Dict]:
    """
    读取本地 news_data.json，与当次抓取的条目合并去重。

    去重策略:
      1. URL 完全相同 → 已存在，忽略新条目，保留旧条目的 added_date
      2. URL 不同但标题高度相似 (≥85%) → 标记 possible_duplicate=True，仍保留
      3. 完全新条目 → 加入

    历史全量保留（不清理、不限每栏目条数），按发布日期降序写回 news_data.json。
    """
    existing: Dict[str, Dict] = {}       # id → entry
    existing_urls: Dict[str, str] = {}   # link → id (快速 URL 查重)

    # ---- 读取历史数据 ----
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r", encoding="utf-8") as f:
                old_entries = json.load(f)
            for e in old_entries:
                eid = e.get("id", "")
                elink = e.get("link", "").strip()
                if eid:
                    existing[eid] = e
                if elink:
                    existing_urls[elink] = eid
            logger.info("读取本地 %d 条历史数据", len(old_entries))
        except (json.JSONDecodeError, IOError) as e:
            logger.warning("本地数据读取失败: %s，将重新初始化", e)

    # ---- 合并: URL 去重 + 标题相似检测 ----
    new_count = 0
    dup_url_count = 0
    dup_title_count = 0

    for item in new_entries:
        link = item["link"].strip()
        item_id = item["id"]

        # 1) URL 完全匹配 → 跳过
        if link in existing_urls:
            dup_url_count += 1
            continue

        # 2) 标题相似检测（已有条目中逐个比对）
        is_title_dup = False
        for existing_item in existing.values():
            if titles_similar(item["title"], existing_item.get("title", "")):
                is_title_dup = True
                break

        if is_title_dup:
            item["possible_duplicate"] = True
            dup_title_count += 1

        # 3) 加入
        existing[item_id] = item
        existing_urls[link] = item_id
        new_count += 1

    logger.info(
        "合并: +%d 新条目, 跳过 %d 条(URL重复), 标记 %d 条(疑似标题重复)",
        new_count, dup_url_count, dup_title_count,
    )

    merged = list(existing.values())

    # ---- 排序（published 降序）----
    merged.sort(key=lambda x: x.get("published", ""), reverse=True)

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info("合并后共 %d 条数据，已写入 %s", len(merged), DATA_FILE)
    except IOError as e:
        logger.error("写入 %s 失败: %s", DATA_FILE, e)

    return merged


# ===================================================================
# 核心爬取流程（Web 手动/定时/补爬与 CLI --manual 共用）
# ===================================================================
def run_crawl() -> None:
    """执行一次完整的抓取→富化→附件→合并→渲染流程。"""
    logger.info("=" * 50)
    logger.info("全球资讯聚合器 - 开始爬取 [%s]", TODAY_STR)
    logger.info("=" * 50)

    # [1/5] 抓取 RSS
    logger.info("[1/5] 抓取 RSS...")
    entries = fetch.fetch_all()

    if not entries:
        logger.warning("未抓取到任何条目，检查网络连接或 RSS 源是否可用。")

    # [2/5] 详情富化（原位挂 entry["detail"]，config 禁用时直接返回）
    logger.info("[2/5] 详情富化...")
    detail.enrich(entries)

    # [3/5] 附件归档 — 必须在 merge_data 之前：
    #       merge_data 按 URL 去重会跳过旧条目，附件要先下好才不会丢
    #       seen_urls 跨条目去重，避免 Guardian 页脚全站 PDF 被重复下载
    logger.info("[3/5] 附件归档...")
    cfg = fetch.load_config()
    att_enabled = bool((cfg.get("attachment") or {}).get("enabled", True))
    proxy = cfg.get("proxy")
    seen_urls: set = set()
    for entry in entries:
        if att_enabled and entry.get("detail"):
            entry["attachments"] = attachments.download_all(entry, proxy, seen_urls)
        else:
            entry["attachments"] = []   # 保证字段存在

    # [4/5] 合并去重（全量保留历史）
    logger.info("[4/5] 合并本地数据、去重...")
    merged = merge_data(entries)

    # [5/5] 渲染 + 存档
    logger.info("[5/5] 渲染存档...")
    html = render.generate_html(merged)
    render.archive_html(html)

    logger.info("=" * 50)
    logger.info("完成！请在浏览器中打开: %s", render.HTML_FILE)
    logger.info("=" * 50)
