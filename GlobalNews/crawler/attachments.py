# -*- coding: utf-8 -*-
"""PDF 等附件下载归档到 attachments/YYYY-MM/。"""
import os, re, time, logging
from datetime import datetime
from typing import Dict, List

from crawler.fetch import build_session, load_config
from crawler.sources import RSS_SOURCES

logger = logging.getLogger("crawler")

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ATTACH_DIR = os.path.join(BASE_DIR, "attachments")

_PDF_NAME_RE = re.compile(r'[^/\\?=]+\.pdf', re.IGNORECASE)
_MAX_PER_ENTRY = 5   # 单条新闻最多保存 5 个附件


def _source_needs_proxy(name: str) -> bool:
    for s in RSS_SOURCES:
        if s["name"] == name:
            return bool(s.get("needs_proxy"))
    return False


def _filename_from_url(url: str) -> str:
    """从 URL 提取 PDF 文件名；arXiv 风格 /pdf/<id> 补 .pdf；取不到时兜底 file.pdf。"""
    m = _PDF_NAME_RE.search(url)
    if m:
        return m.group(0)[:120]
    # 无 .pdf 后缀（如 https://arxiv.org/pdf/2609.00002v1）：路径含 /pdf 时取末段补 .pdf
    path = url.split("?", 1)[0]
    if "/pdf" in path:
        seg = path.rstrip("/").rsplit("/", 1)[-1]
        if seg:
            return (seg + ".pdf")[:120]
    return "file.pdf"


def download_all(entry: Dict, proxy: str = None, seen_urls: set = None) -> List[Dict]:
    """下载 entry["detail"]["pdf_links"] 中的附件，按月归档到 attachments/YYYY-MM/。

    - proxy 为 None 时读 config.json 的 proxy；显式传 "" 可强制直连（测试/冒烟用）
    - seen_urls：单次运行内已下载过的 URL 集合，跨条目去重
      （防止 Guardian 等站点页脚全站 PDF 在每个详情条目重复下载）
    - attachment.enabled 为 False 或无链接时返回 []
    - HEAD 预检 Content-Length，超过 attachment.max_mb（默认 20）跳过不下载
    - 单条最多 _MAX_PER_ENTRY 个附件；单附件失败仅告警，不影响其余
    - 返回 [{"filename", "size", "url"}, ...]
    """
    cfg = load_config()
    att_cfg = cfg.get("attachment", {}) or {}
    if not att_cfg.get("enabled", True):
        return []

    links = (entry.get("detail") or {}).get("pdf_links") or []
    if not links:
        return []

    if seen_urls is None:
        seen_urls = set()

    if proxy is None:
        proxy = cfg.get("proxy", "")
    max_bytes = int(att_cfg.get("max_mb", 20)) * 1024 * 1024
    month_dir = os.path.join(ATTACH_DIR, datetime.now().strftime("%Y-%m"))

    saved: List[Dict] = []
    session = build_session(_source_needs_proxy(entry.get("source", "")), proxy)
    try:
        for url in links[:_MAX_PER_ENTRY]:
            if url in seen_urls:
                continue   # 本次运行已下载过（如 Guardian 页脚全站 PDF）
            try:
                # HEAD 预检大小：无 Content-Length 头视为 0（不跳过）
                h = session.head(url, timeout=15, allow_redirects=True)
                try:
                    declared = int(h.headers.get("Content-Length") or 0)
                except (TypeError, ValueError):
                    declared = 0
                if declared > max_bytes:
                    logger.info("附件超过 %dMB 限制，跳过: %s",
                                max_bytes // (1024 * 1024), url)
                    continue

                r = session.get(url, timeout=60)
                r.raise_for_status()
                os.makedirs(month_dir, exist_ok=True)
                fname = _filename_from_url(url)
                with open(os.path.join(month_dir, fname), "wb") as f:
                    f.write(r.content)
                saved.append({"filename": fname, "size": len(r.content), "url": url})
                seen_urls.add(url)
                logger.info("附件已归档: %s (%d bytes)", fname, len(r.content))
                time.sleep(1)  # 限速
            except Exception as e:
                logger.warning("附件下载失败 %s: %s", url, e)
                continue
    finally:
        session.close()
    return saved
