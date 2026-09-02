#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS 抓取 + 代理管理。
境外源（needs_proxy=True）走 config.json 配置的代理；国内源强制直连
（清空 proxies 并禁用 trust_env，防系统代理劫持国内流量）。

依赖: pip install feedparser requests
可选: pip install deep-translator   # 英文→中文翻译
"""

import os
import json
import re
import hashlib
import logging
import time
import concurrent.futures
from datetime import datetime
from typing import List, Dict

import feedparser
import requests

from crawler.sources import RSS_SOURCES

# 可选翻译支持 (deep-translator 基于 Google Translate，免费、无需 API key)
try:
    from deep_translator import GoogleTranslator
    _translator = GoogleTranslator(source="auto", target="zh-CN")
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# 中文字符范围，用于检测文本是否已是中文
_CJK_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿]')

# 日志配置（含 Windows 控制台 UTF-8 重定向）留在各入口文件，本模块只取 logger
logger = logging.getLogger("crawler")

# ---------------------------------------------------------------------------
# 文件路径 — fetch.py 上两级目录即 GlobalNews/
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

TODAY_STR = datetime.now().strftime("%Y-%m-%d")


# ===================================================================
# 配置读取
# ===================================================================
def load_config() -> Dict:
    """读取 GlobalNews/config.json，文件不存在或损坏时返回 {}。"""
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (IOError, json.JSONDecodeError):
        return {}


# ===================================================================
# 会话构造（代理管理）
# ===================================================================
def build_session(needs_proxy: bool, proxy: str) -> requests.Session:
    """
    构造带统一 UA 的 RSS 抓取会话。

    needs_proxy 且配置了代理 → http/https 均走该代理；
    否则 proxies 置空。两种情况均 trust_env=False：
    代理会话防止系统环境变量代理覆盖 config 代理，
    直连会话防止系统代理劫持国内流量。
    """
    s = requests.Session()
    s.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })
    if needs_proxy and proxy:
        s.proxies = {"http": proxy, "https": proxy}
    else:
        s.proxies = {}
    s.trust_env = False
    return s


# ===================================================================
# 翻译辅助（英文→中文）
# ===================================================================
_TRANSLATE_TIMEOUT = 5  # 单次翻译最多等 5 秒

def _is_chinese(text: str) -> bool:
    """检测文本是否包含中文字符，是则无需翻译"""
    return bool(_CJK_RE.search(text))

def translate_en_to_zh(text: str) -> str:
    """将英文文本翻译为中文，失败时返回原文。"""
    if not HAS_TRANSLATOR or not text:
        return text
    if _is_chinese(text):
        return text                             # 已是中文，跳过翻译
    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            fut = pool.submit(_translator.translate, text)
            return fut.result(timeout=_TRANSLATE_TIMEOUT)
    except concurrent.futures.TimeoutError:
        logger.debug("翻译超时(>%ds): %s", _TRANSLATE_TIMEOUT, text[:30])
    except Exception:
        logger.debug("翻译失败: %s", text[:30])
    return text


# ===================================================================
# ID 生成（基于链接 MD5）
# ===================================================================
def make_id(link: str) -> str:
    return hashlib.md5(link.strip().encode("utf-8")).hexdigest()


# ===================================================================
# 抓取所有 RSS 源
# ===================================================================
def fetch_all() -> List[Dict]:
    """
    遍历所有 RSS 源，抓取、清洗、翻译。全量保留数据（不截断）。

    - 每源按 needs_proxy 单独建会话：境外走代理，国内强制直连
    - 单源请求超时 15s（代理链路较慢），源间 sleep 1s 限速
    - 丢弃: 无标题 / 无链接 / 摘要为空的条目

    返回:
      [{ "id", "title", "title_zh", "link", "summary", "summary_zh",
         "source", "category", "published", "added_date",
         "possible_duplicate" }, ...]
    """
    entries: List[Dict] = []
    config = load_config()
    proxy = config.get("proxy", "")

    total_fetched = 0
    total_discarded = 0

    for idx, src in enumerate(RSS_SOURCES):
        if idx > 0:
            time.sleep(1)  # 源间限速

        name = src["name"]
        url = src["url"]
        cat = src["category"]
        logger.info("抓取 [%s] %s → %s", cat, name, url)

        session = build_session(src["needs_proxy"], proxy)
        try:
            resp = session.get(url, timeout=15)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)

            if feed.bozo and not feed.entries:
                logger.warning("  Feed 解析警告 (%s): %s", name, feed.bozo_exception)
                continue

            count = 0
            discarded = 0
            for entry in feed.entries:
                title = (entry.get("title", "") or "").strip()
                link = (entry.get("link", "") or "").strip()

                # ---- 丢弃无效条目 ----
                if not title:
                    discarded += 1
                    continue
                if not link:
                    discarded += 1
                    continue

                # ---- 提取并清洗 summary ----
                raw_summary = entry.get("summary", "") or entry.get("description", "") or ""
                summary = re.sub(r"<[^>]+>", "", raw_summary).strip()

                # 丢弃摘要为空的条目
                if not summary:
                    discarded += 1
                    continue

                # 截取前 300 字符
                summary = summary[:300]

                # ---- 翻译标题和摘要（英文→中文；无翻译库时留空） ----
                title_zh = translate_en_to_zh(title) if HAS_TRANSLATOR else ""
                summary_zh = translate_en_to_zh(summary) if HAS_TRANSLATOR else ""

                # ---- 标准化发布日期 ----
                published = ""
                if hasattr(entry, "published_parsed") and entry.published_parsed:
                    try:
                        published = datetime(*entry.published_parsed[:6]).strftime("%Y-%m-%d")
                    except (TypeError, ValueError):
                        published = ""
                if not published:
                    published = TODAY_STR

                entries.append({
                    "id": make_id(link),
                    "title": title,
                    "title_zh": title_zh,
                    "link": link,
                    "summary": summary,
                    "summary_zh": summary_zh,
                    "source": name,
                    "category": cat,
                    "published": published,
                    "added_date": TODAY_STR,
                    "possible_duplicate": False,
                })
                count += 1

            total_fetched += count
            total_discarded += discarded
            logger.info("  获取 %d 条, 丢弃 %d 条", count, discarded)

        except requests.RequestException as e:
            logger.error("  网络请求失败 (%s): %s", name, e)
        except Exception as e:
            logger.error("  未知错误 (%s): %s", name, e)
        finally:
            session.close()

    logger.info("总计抓取 %d 条有效条目, 丢弃 %d 条无效条目", total_fetched, total_discarded)
    return entries
