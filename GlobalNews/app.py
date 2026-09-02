#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Global News v2 — Flask + 内嵌调度器，唯一常驻入口。

启动方式: python app.py → http://localhost:5000
- 手动: 页面"立即更新"按钮 → POST /crawl → 后台线程爬取
- 定时: 每周六 09:00 自动爬取（schedule 库，调度线程）
- 补偿: 启动时若数据超过 7 天未更新，60 秒后自动补爬
"""

import os
import sys
import json
import time
import threading
import logging
import importlib.util
from datetime import datetime, timedelta

from flask import Flask, jsonify, send_from_directory

# schedule 库可选（缺库时禁用定时，仍可手动爬取）
try:
    import schedule as schedule_lib
    HAS_SCHEDULE = True
except ImportError:
    schedule_lib = None
    HAS_SCHEDULE = False

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------------------
# 加载旧版 crawler.py 的 run_crawl
# 注意: 包目录 crawler/（Task 7 前为空壳）会遮蔽同名的 crawler.py 文件，
# `from crawler import run_crawl` 会解析到包而失败，故用 importlib 从文件显式加载。
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "legacy_crawler", os.path.join(BASE_DIR, "crawler.py")
)
_legacy = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_legacy)
run_crawl = _legacy.run_crawl

app = Flask(__name__)

# 爬取状态（手动 / 定时 / 补爬共用一把互斥锁）
_crawl_lock = threading.Lock()
_crawl_in_progress = False
_crawl_result = None

logger = logging.getLogger("web")


def _safe_run_crawl(trigger: str) -> None:
    """带互斥锁的爬取入口，供手动、定时、启动补偿共用。

    非阻塞抢锁：拿不到说明已有爬取进行中，记日志并跳过。
    """
    global _crawl_in_progress, _crawl_result

    if not _crawl_lock.acquire(blocking=False):
        logger.info("已有爬取进行中，跳过(%s)", trigger)
        return

    _crawl_in_progress = True
    try:
        logger.info("爬取开始 (trigger=%s)", trigger)
        run_crawl()
        _crawl_result = {
            "ok": True,
            "trigger": trigger,
            "finished_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        }
        logger.info("爬取完成 (trigger=%s)", trigger)
    except Exception as e:
        logger.error("爬取失败 (trigger=%s): %s", trigger, e)
        _crawl_result = {"ok": False, "trigger": trigger, "error": str(e)}
    finally:
        _crawl_in_progress = False
        _crawl_lock.release()


def _latest_added_date() -> str:
    """读取 news_data.json 中所有条目 added_date 的最大值；文件不存在或损坏返回 ''。"""
    data_file = os.path.join(BASE_DIR, "news_data.json")
    if not os.path.exists(data_file):
        return ""
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, list):
            return ""
        return max(
            (e.get("added_date", "") for e in data if isinstance(e, dict)),
            default="",
        )
    except (json.JSONDecodeError, OSError):
        return ""


def _next_saturday_nine() -> str:
    """计算下一个周六 09:00（周六=weekday 5；今天周六且已过 9 点则算下周）。"""
    now = datetime.now()
    days_ahead = (5 - now.weekday()) % 7
    if days_ahead == 0 and now.hour >= 9:
        days_ahead = 7
    next_run = (now + timedelta(days=days_ahead)).replace(hour=9, minute=0, second=0, microsecond=0)
    return next_run.strftime("%Y-%m-%d %H:%M")


def _scheduler_loop() -> None:
    """调度线程: 注册每周六 09:00 任务并周期性检查触发。"""
    schedule_lib.every().saturday.at("09:00").do(_safe_run_crawl, trigger="scheduled")
    logger.info("调度器已启动: 每周六 09:00 自动爬取，下次: %s", _next_saturday_nine())
    while True:
        schedule_lib.run_pending()
        time.sleep(60)


@app.route("/")
def index():
    """返回最新生成的 news.html，不存在时从模板生成一份"""
    html_path = os.path.join(BASE_DIR, "news.html")
    if not os.path.exists(html_path):
        # 从模板生成一个空数据的页面
        tpl_path = os.path.join(BASE_DIR, "template.html")
        if os.path.exists(tpl_path):
            with open(tpl_path, "r", encoding="utf-8") as f:
                tpl = f.read()
            html = tpl.replace("__JSON_DATA_PLACEHOLDER__", "[]")
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html)
    return send_from_directory(BASE_DIR, "news.html")


@app.route("/crawl", methods=["POST"])
def trigger_crawl():
    """触发手动爬取（后台线程，不阻塞）"""
    global _crawl_in_progress, _crawl_result

    if _crawl_in_progress:
        return jsonify({"ok": False, "error": "正在爬取中，请稍候"}), 429

    _crawl_in_progress = True
    _crawl_result = None
    thread = threading.Thread(target=_safe_run_crawl, args=("manual",), daemon=True)
    thread.start()
    return jsonify({"ok": True, "message": "爬取已启动"})


@app.route("/status")
def crawl_status():
    """查询爬取状态"""
    return jsonify({
        "running": _crawl_in_progress,
        "result": _crawl_result,
        "next_run": _next_saturday_nine(),
    })


@app.route("/attachments/<path:subpath>")
def attachments(subpath):
    """附件下载：attachments/2026-09/xxx.pdf → /attachments/2026-09/xxx.pdf"""
    return send_from_directory(os.path.join(BASE_DIR, "attachments"), subpath)


if __name__ == "__main__":
    # Windows 控制台默认 gbk，logging 输出时会乱码；强制 stdout/stderr 用 utf-8
    for _fh in (sys.stdout, sys.stderr):
        if hasattr(_fh, "reconfigure"):
            _fh.reconfigure(encoding="utf-8")
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    logger.info("=" * 50)
    logger.info("Global News Web Server 启动")
    logger.info("浏览器打开: http://localhost:5000")
    logger.info("=" * 50)

    # ---- 定时调度线程 ----
    if HAS_SCHEDULE:
        threading.Thread(target=_scheduler_loop, daemon=True).start()
    else:
        logger.error("缺少 schedule 库，定时爬取已禁用。请运行: pip install schedule")

    # ---- 启动补偿: 数据为空或超过 7 天未更新，60 秒后自动补爬 ----
    _latest = _latest_added_date()
    _stale = True
    if _latest:
        try:
            _stale = (datetime.now() - datetime.strptime(_latest, "%Y-%m-%d")).days > 7
        except ValueError:
            _stale = True
    if _stale:
        logger.info("数据已超过 7 天未更新（最新: %s），60 秒后自动补爬", _latest or "无数据")
        _timer = threading.Timer(60, _safe_run_crawl, args=("startup",))
        _timer.daemon = True
        _timer.start()

    app.run(host="0.0.0.0", port=5000, debug=False)
