# -*- coding: utf-8 -*-
"""逐源探测可用性：HTTP 状态 + RSS 是否解析出条目。"""
import concurrent.futures
from typing import Dict, List
import feedparser
from crawler.sources import RSS_SOURCES
from crawler.fetch import build_session, load_config

def check_all() -> List[Dict]:
    cfg = load_config()
    proxy = cfg.get("proxy", "")
    def _probe(src):
        s = build_session(src["needs_proxy"], proxy)
        try:
            r = s.get(src["url"], timeout=15)
            feed = feedparser.parse(r.content)
            n = len(feed.entries)
            return {**src, "status": r.status_code, "entries": n,
                    "ok": r.ok and n > 0}
        except Exception as e:
            return {**src, "status": 0, "entries": 0, "ok": False, "error": str(e)}
        finally:
            s.close()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        return list(pool.map(_probe, RSS_SOURCES))

def print_report(results: List[Dict]) -> None:
    for r in results:
        flag = "OK " if r["ok"] else "FAIL"
        print(f"[{flag}] {r['name']:<24} HTTP {r['status']:<4} {r['entries']} 条"
              + (f"  {r.get('error','')}" if not r["ok"] else ""))
