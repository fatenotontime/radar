#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Global News Aggregator - RSS Crawler
抓取全球资讯 RSS 源，自动分类、URL 去重、合并历史，生成静态 HTML。

运行方式:
    python crawler.py --manual      # 手动立即爬取一次
    python crawler.py               # 启动调度器，每周六 09:00 自动运行

依赖: pip install feedparser requests schedule
"""

import os
import sys
import json
import re
import hashlib
import logging
import argparse
import time
import concurrent.futures
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Optional
from difflib import SequenceMatcher

import feedparser
import requests

try:
    import schedule as schedule_lib
    HAS_SCHEDULE = True
except ImportError:
    HAS_SCHEDULE = False

# 可选翻译支持 (deep-translator 基于 Google Translate，免费、无需 API key)
try:
    from deep_translator import GoogleTranslator
    _translator = GoogleTranslator(source="auto", target="zh-CN")
    HAS_TRANSLATOR = True
except ImportError:
    HAS_TRANSLATOR = False

# 中文字符范围，用于检测文本是否已是中文
_CJK_RE = re.compile(r'[一-鿿㐀-䶿豈-﫿]')

# ---------------------------------------------------------------------------
# 日志配置
# ---------------------------------------------------------------------------
# Windows 控制台默认 gbk，logging 输出时会乱码；强制 stdout/stderr 用 utf-8
for _fh in (sys.stdout, sys.stderr):
    if hasattr(_fh, "reconfigure"):
        _fh.reconfigure(encoding="utf-8")
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("crawler")

# ---------------------------------------------------------------------------
# RSS 源配置 — 平铺列表，分类由 auto_tag() 自动判定
# ---------------------------------------------------------------------------
RSS_SOURCES: List[Dict[str, str]] = [
    # ---- 中文源（国内可访问，放前面优先抓取） ----
    {"name": "澎湃新闻",               "url": "https://www.thepaper.cn/rss.xml"},
    {"name": "机器之心",               "url": "https://www.jiqizhixin.com/rss.xml"},
    {"name": "36氪",                   "url": "https://36kr.com/feed"},
    # ---- World ----
    {"name": "China Daily World",       "url": "https://www.chinadaily.com.cn/rss/world_rss.xml"},
    # Xinhua English World RSS endpoint changed, 404
    # {"name": "Xinhua English World",    "url": "https://english.news.cn/rss/world.xml"},
    # ---- Science ----
    {"name": "ScienceDaily Chemistry",  "url": "https://www.sciencedaily.com/rss/matter_energy/chemistry.xml"},
    {"name": "ScienceDaily Biology",    "url": "https://www.sciencedaily.com/rss/plants_animals/biology.xml"},
    {"name": "ScienceDaily Materials",  "url": "https://www.sciencedaily.com/rss/matter_energy/materials_science.xml"},
    {"name": "Phys.org Chemistry",      "url": "https://phys.org/rss-feed/chemistry-news/"},
    {"name": "Phys.org Biology",        "url": "https://phys.org/rss-feed/biology-news/"},
    # Phys.org Materials RSS: 404
    # {"name": "Phys.org Materials",      "url": "https://phys.org/rss-feed/materials-news/"},
    {"name": "JACS (ACS)",              "url": "https://pubs.acs.org/action/showFeed?type=etoc&feed=rss&jc=jacsat"},
    {"name": "Angew. Chem. (Wiley)",    "url": "https://onlinelibrary.wiley.com/feed/15212665/most-recent"},
    {"name": "Adv. Mater. (Wiley)",     "url": "https://onlinelibrary.wiley.com/feed/15214095/most-recent"},
    # Cell in press: 403 Forbidden
    # {"name": "Cell (in press)",         "url": "https://www.cell.com/cell/inpress.rss"},
    # ---- AI ----
    {"name": "arXiv cs.AI",            "url": "https://rss.arxiv.org/rss/cs.AI"},
    {"name": "arXiv cs.CL",            "url": "https://rss.arxiv.org/rss/cs.CL"},
    {"name": "arXiv cs.LG",            "url": "https://rss.arxiv.org/rss/cs.LG"},
    # Google AI Blog: RSS feed deprecated / hangs on fetch
    # {"name": "Google AI Blog",         "url": "https://ai.googleblog.com/feeds/posts/default"},
]

# 分类标签 → 显示名称
CATEGORY_MAP = {
    "world":   "国际形势",
    "science": "前沿科研",
    "ai":      "AI 成果",
}

# ---------------------------------------------------------------------------
# 文件路径
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "news_data.json")
HTML_FILE = os.path.join(BASE_DIR, "news.html")
ARCHIVE_DIR = os.path.join(BASE_DIR, "archive")
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

TODAY_STR = datetime.now().strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# 抓取上限
# ---------------------------------------------------------------------------
MAX_PER_CRAWL = 30      # 每次爬取最多保留条数
MAX_PER_CATEGORY = 30   # 每个栏目最多保留条数


# ===================================================================
# 1. 根据来源名称自动打分类标签
# ===================================================================
def auto_tag(source_name: str) -> str:
    """
    World  : China Daily, Xinhua
    Science: ScienceDaily, Phys.org, ACS, Wiley, Cell
    AI     : arXiv, Google AI
    """
    name_lower = source_name.lower()
    # World
    if any(kw in name_lower for kw in ["china daily", "xinhua", "澎湃"]):
        return "world"
    # Science
    if any(kw in name_lower for kw in [
        "sciencedaily", "phys.org", "acs", "wiley", "cell",
    ]):
        return "science"
    # AI
    if any(kw in name_lower for kw in ["arxiv", "google ai", "机器之心", "36氪"]):
        return "ai"
    # fallback
    logger.warning("未识别分类的源: %s，归入 science", source_name)
    return "science"


# ===================================================================
# 1b. 翻译辅助（英文→中文）
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
# 2. ID 生成（基于链接 MD5）
# ===================================================================
def make_id(link: str) -> str:
    return hashlib.md5(link.strip().encode("utf-8")).hexdigest()


# ===================================================================
# 3. 标题相似度检测（用于辅助去重）
# ===================================================================
def titles_similar(a: str, b: str, threshold: float = 0.85) -> bool:
    """两个标题的相似度 >= threshold 时返回 True"""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio() >= threshold


# ===================================================================
# 4. 抓取所有 RSS 源
# ===================================================================
def fetch_all() -> List[Dict]:
    """
    遍历所有 RSS 源，抓取、清洗、自动分类。
    丢弃: 无标题 / 摘要为空的条目。
    返回:
      [{ "id", "title", "link", "summary", "source", "category",
         "published", "added_date", "possible_duplicate" }, ...]
    """
    entries: List[Dict] = []
    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
        ),
        "Accept": "application/rss+xml, application/xml, text/xml, */*",
    })

    total_fetched = 0
    total_discarded = 0

    for src in RSS_SOURCES:
        name = src["name"]
        url = src["url"]
        cat = auto_tag(name)
        logger.info("抓取 [%s] %s → %s", cat, name, url)

        try:
            resp = session.get(url, timeout=8)
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

                # ---- 翻译标题和摘要（英文→中文） ----
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

                entry_id = make_id(link)

                entries.append({
                    "id": entry_id,
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

                # 达到抓取上限即停止
                if len(entries) >= MAX_PER_CRAWL:
                    break

            total_fetched += count
            total_discarded += discarded
            logger.info("  获取 %d 条, 丢弃 %d 条", count, discarded)

            if len(entries) >= MAX_PER_CRAWL:
                logger.info("已达上限 %d 条，停止抓取", MAX_PER_CRAWL)
                break

        except requests.RequestException as e:
            logger.error("  网络请求失败 (%s): %s", name, e)
        except Exception as e:
            logger.error("  未知错误 (%s): %s", name, e)

    logger.info("总计抓取 %d 条有效条目, 丢弃 %d 条无效条目", total_fetched, total_discarded)
    return entries


# ===================================================================
# 5. 与历史数据合并去重 + 月度清理
# ===================================================================
def merge_data(new_entries: List[Dict]) -> List[Dict]:
    """
    读取本地 news_data.json，与当次抓取的条目合并去重。

    去重策略:
      1. URL 完全相同 → 已存在，忽略新条目，保留旧条目的 added_date
      2. URL 不同但标题高度相似 (≥85%) → 标记 possible_duplicate=True，仍保留
      3. 完全新条目 → 加入

    每月清理: 删除 added_date 超过 30 天的旧记录（仅月初执行一次）。
    按发布日期降序排列，写回 news_data.json。
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

    # ---- 月度清理 ----
    merged = _monthly_cleanup(merged)

    # ---- 排序 & 每栏目最多保留 MAX_PER_CATEGORY 条 ----
    merged.sort(key=lambda x: x.get("published", ""), reverse=True)

    seen_cats: Dict[str, int] = {}
    capped: List[Dict] = []
    for entry in merged:
        cat = entry.get("category", "science")
        count = seen_cats.get(cat, 0)
        if count >= MAX_PER_CATEGORY:
            continue
        seen_cats[cat] = count + 1
        capped.append(entry)

    if len(capped) < len(merged):
        logger.info("每栏目上限 %d 条: %d → %d", MAX_PER_CATEGORY, len(merged), len(capped))
    merged = capped

    try:
        with open(DATA_FILE, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)
        logger.info("合并后共 %d 条数据，已写入 %s", len(merged), DATA_FILE)
    except IOError as e:
        logger.error("写入 %s 失败: %s", DATA_FILE, e)

    return merged


def _monthly_cleanup(entries: List[Dict]) -> List[Dict]:
    """
    若距离上次清理已过一个月，删除 added_date 早于 30 天前的条目。
    清理状态记录在 config.json。
    """
    config = {}
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                config = json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    last_cleanup = config.get("last_cleanup", "")
    current_month = TODAY_STR[:7]  # YYYY-MM

    if last_cleanup == current_month:
        return entries  # 本月已清理过

    # 删除 added_date < 3 周前的条目
    cutoff = (datetime.now() - timedelta(weeks=3)).strftime("%Y-%m-%d")
    before = len(entries)
    entries = [e for e in entries if e.get("added_date", "") >= cutoff]
    removed = before - len(entries)

    if removed > 0:
        logger.info("月度清理: %d → %d 条 (删除 %d 条超过30天的旧记录)", before, len(entries), removed)

    # 更新清理标记
    config["last_cleanup"] = current_month
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(config, f, ensure_ascii=False)
    except IOError as e:
        logger.error("写入 config.json 失败: %s", e)

    return entries


# ===================================================================
# 6. HTML 模板文件路径
# ===================================================================
TEMPLATE_FILE = os.path.join(BASE_DIR, "template.html")


# ===================================================================
# 7. 生成 news.html
# ===================================================================
def generate_html(entries: List[Dict]) -> str:
    """
    从 template.html 读取模板，将 news_data.json 中的全部数据注入，
    生成自包含的 news.html 阅读页面。
    """
    # 读取模板文件
    try:
        with open(TEMPLATE_FILE, "r", encoding="utf-8") as f:
            template = f.read()
    except (IOError, FileNotFoundError) as e:
        logger.error("读取模板文件 %s 失败: %s", TEMPLATE_FILE, e)
        sys.exit(1)

    json_str = json.dumps(entries, ensure_ascii=False)
    html_content = template.replace("__JSON_DATA_PLACEHOLDER__", json_str)

    try:
        with open(HTML_FILE, "w", encoding="utf-8") as f:
            f.write(html_content)
        logger.info("HTML 已生成 → %s (%d 条)", HTML_FILE, len(entries))
    except IOError as e:
        logger.error("写入 %s 失败: %s", HTML_FILE, e)
        sys.exit(1)

    return html_content


# ===================================================================
# 8. 按周存档
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


# ===================================================================
# 9. 核心爬取流程（供手动和调度共用）
# ===================================================================
def run_crawl() -> None:
    """执行一次完整的抓取→合并→生成→存档流程。"""
    logger.info("=" * 50)
    logger.info("全球资讯聚合器 - 开始爬取 [%s]", TODAY_STR)
    logger.info("=" * 50)

    # [1/4] 抓取
    logger.info("[1/4] 抓取 RSS 源...")
    new_entries = fetch_all()

    if not new_entries:
        logger.warning("未抓取到任何条目，检查网络连接或 RSS 源是否可用。")

    # [2/4] 合并去重 + 月度清理
    logger.info("[2/4] 合并本地数据、去重、清理...")
    merged = merge_data(new_entries)

    # [3/4] 生成 HTML
    logger.info("[3/4] 生成 HTML 页面...")
    html_content = generate_html(merged)

    # [4/4] 存档
    logger.info("[4/4] 存档到 archive/ ...")
    archive_html(html_content)

    logger.info("=" * 50)
    logger.info("完成！请在浏览器中打开: %s", HTML_FILE)
    logger.info("=" * 50)


# ===================================================================
# 10. 主入口
# ===================================================================
def main() -> None:
    parser = argparse.ArgumentParser(
        description="全球资讯聚合 RSS 爬虫",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
使用示例:
  python crawler.py --manual    手动立即爬取一次
  python crawler.py             启动调度器，每周六 09:00 自动运行
        """,
    )
    parser.add_argument(
        "--manual", action="store_true",
        help="手动立即执行一次爬取（不启动调度器）",
    )
    parser.add_argument(
        "--check", action="store_true",
        help="探测所有源可用性",
    )
    args = parser.parse_args()

    # ---- 源可用性探测 ----
    if args.check:
        from crawler.check import check_all, print_report
        print_report(check_all())
        return

    # ---- 手动模式 ----
    if args.manual:
        run_crawl()
        return

    # ---- 调度模式 ----
    if not HAS_SCHEDULE:
        logger.error(
            "缺少 schedule 库，无法启动调度器。"
            "请运行: pip install schedule"
            "或使用 --manual 手动爬取。"
        )
        sys.exit(1)

    logger.info("调度器已启动，每周六 09:00 自动爬取。按 Ctrl+C 停止。")
    logger.info("提示: 使用 --manual 可立即手动爬取一次。")

    schedule_lib.every().saturday.at("09:00").do(run_crawl)

    # 启动后立即执行一次（如果当天是周六且尚未到9点，先跑一次）
    now = datetime.now()
    if now.weekday() == 5 and now.hour < 9:  # 周六且未到9点
        logger.info("今天是周六，提前执行一次初始爬取...")
        run_crawl()

    while True:
        schedule_lib.run_pending()
        time.sleep(60)


if __name__ == "__main__":
    main()
