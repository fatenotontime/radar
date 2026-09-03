# -*- coding: utf-8 -*-
"""多级网页抓取：对 top N 条目进入原文页提取正文/首图/PDF 链接。"""
import os, re, time, hashlib, logging
from datetime import datetime, timedelta
from typing import Dict, List
from urllib.parse import urlparse, urljoin

import trafilatura

from crawler.fetch import build_session, load_config
from crawler.sources import RSS_SOURCES

logger = logging.getLogger("crawler")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CACHE_DIR = os.path.join(BASE_DIR, "cache")
CACHE_TTL_DAYS = 7
DETAIL_TEXT_LIMIT = 2000
PAGE_TIMEOUT = 15

_SOURCE_WEIGHT = {s["name"]: s.get("weight", 1) for s in RSS_SOURCES}
_SOURCE_PROXY = {s["name"]: bool(s.get("needs_proxy")) for s in RSS_SOURCES}
_last_fetch_by_domain: Dict[str, float] = {}


# ===================================================================
# 域名级限速：同域名两次请求之间至少间隔 min_gap 秒
# ===================================================================
def _domain_throttle(url: str, min_gap: float = 2.0) -> None:
    domain = urlparse(url).netloc
    last = _last_fetch_by_domain.get(domain)
    if last is not None:
        wait = min_gap - (time.time() - last)
        if wait > 0:
            time.sleep(wait)
    _last_fetch_by_domain[domain] = time.time()


# ===================================================================
# 缓存路径：链接 MD5 → GlobalNews/cache/<md5>.html
# ===================================================================
def _cache_path(link: str) -> str:
    digest = hashlib.md5(link.encode("utf-8")).hexdigest()
    return os.path.join(CACHE_DIR, digest + ".html")


def cache_is_fresh(path: str) -> bool:
    """缓存文件存在且 mtime 距今不足 7 天才算新鲜。"""
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return False
    return datetime.now() - datetime.fromtimestamp(mtime) < timedelta(days=CACHE_TTL_DAYS)


# ===================================================================
# 条目筛选：每个分类按 (源权重, 发布日期) 降序取前 top_n
# ===================================================================
def select_for_detail(entries: List[Dict], top_n: int) -> List[Dict]:
    picked: List[Dict] = []
    for cat in ("world", "science", "ai"):
        pool = [e for e in entries if e.get("category") == cat]
        pool.sort(
            key=lambda e: (_SOURCE_WEIGHT.get(e.get("source"), 1), e.get("published", "")),
            reverse=True,
        )
        picked.extend(pool[:top_n])
    return picked


# ===================================================================
# PDF 链接提取：href 里以 .pdf 结尾（或含 .pdf 查询串）的地址，
# 相对路径按页面 URL 解析为绝对地址，去重排序
# ===================================================================
def extract_pdf_links(html: str, base_url: str) -> List[str]:
    hrefs = re.findall(r'href=["\']([^"\']+\.pdf[^"\']*)["\']', html, re.IGNORECASE)
    return sorted(set(urljoin(base_url, h) for h in hrefs))


# ===================================================================
# 单条详情抓取（带缓存）
# ===================================================================
def fetch_detail(entry: Dict, proxy: str) -> Dict:
    os.makedirs(CACHE_DIR, exist_ok=True)
    link = entry["link"]
    cpath = _cache_path(link)

    if cache_is_fresh(cpath):
        with open(cpath, "r", encoding="utf-8") as f:
            html = f.read()
    else:
        needs_proxy = _SOURCE_PROXY.get(entry.get("source"), False)
        session = build_session(needs_proxy, proxy)
        try:
            _domain_throttle(link)
            resp = session.get(link, timeout=PAGE_TIMEOUT)
            resp.raise_for_status()
            html = resp.text
        finally:
            session.close()
        with open(cpath, "w", encoding="utf-8") as f:
            f.write(html)

    # 正文提取（正文为空时返回空串）
    text = trafilatura.extract(
        html, include_images=True, include_links=True, favor_recall=True
    ) or ""

    # 首图：页面第一个 <img src="...">
    m = re.search(r'<img[^>]+src=["\']([^"\']+)["\']', html)
    first_img = m.group(1) if m else ""

    # PDF 链接：href 里以 .pdf 结尾（或含 .pdf 查询串）的地址，相对路径解析为绝对地址
    pdf_links = extract_pdf_links(html, link)

    # arXiv 特判：abs 页对应的 PDF 就是 /pdf/ 同编号页
    if "arxiv.org/abs/" in link:
        pdf_links = [link.replace("/abs/", "/pdf/")]

    return {
        "fetched": True,
        "text": text[:DETAIL_TEXT_LIMIT],
        "image": first_img,
        "pdf_links": pdf_links,
    }


# ===================================================================
# 批量富化：对 top N 条目挂 entry["detail"]
# ===================================================================
def enrich(entries: List[Dict]) -> List[Dict]:
    cfg = load_config()
    detail_cfg = cfg.get("detail_crawl") or {}
    if not detail_cfg.get("enabled", False):
        return entries

    proxy = cfg.get("proxy", "")
    top_n = detail_cfg.get("top_n", 10)

    for entry in select_for_detail(entries, top_n):
        try:
            entry["detail"] = fetch_detail(entry, proxy)
        except Exception as e:
            logger.warning("详情抓取失败(%s): %s", entry.get("source", "?"), e)
            entry["detail"] = {"fetched": False}
    return entries
