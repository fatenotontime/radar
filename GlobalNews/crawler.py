#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""CLI 入口：python crawler.py --manual | --check（v2 起 Web/调度统一走 app.py）"""
import sys, logging

def _setup_log():
    for _fh in (sys.stdout, sys.stderr):
        if hasattr(_fh, "reconfigure"):
            _fh.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s [%(levelname)s] %(message)s",
                        datefmt="%Y-%m-%d %H:%M:%S")

if __name__ == "__main__":
    import argparse
    _setup_log()
    parser = argparse.ArgumentParser(description="全球资讯聚合 RSS 爬虫 v2")
    parser.add_argument("--manual", action="store_true", help="立即爬取一次")
    parser.add_argument("--check", action="store_true", help="探测所有源可用性")
    args = parser.parse_args()
    if args.check:
        from crawler.check import check_all, print_report
        print_report(check_all())
    else:
        from crawler.pipeline import run_crawl
        run_crawl()
