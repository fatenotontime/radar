# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from crawler.detail import select_for_detail, cache_is_fresh

def test_select_picks_top_n_per_category():
    # weight 高、日期新的优先；每分类最多 top_n 条
    entries = [{"id": str(i), "category": c, "source": s, "published": p}
               for c in ("world", "ai") for i, (s, p) in enumerate(
                   [("BBC World", "2026-09-01"), ("China Daily World", "2026-09-02"), ("NYT World", "2026-09-03")])]
    picked = select_for_detail(entries, top_n=2)
    assert sum(1 for e in picked if e["category"] == "world") == 2
    assert sum(1 for e in picked if e["category"] == "ai") == 2

def test_select_prefers_higher_weight():
    entries = [
        {"id": "1", "category": "ai", "source": "arXiv cs.AI", "published": "2026-09-01"},
        {"id": "2", "category": "ai", "source": "未知源", "published": "2026-09-02"},
    ]
    picked = select_for_detail(entries, top_n=1)
    assert picked[0]["id"] == "1"

def test_cache_fresh_within_7_days(tmp_path):
    import os
    f = tmp_path / "abc.html"
    f.write_text("x", encoding="utf-8")
    assert cache_is_fresh(str(f)) is True
    old = datetime.now() - timedelta(days=8)
    os.utime(f, (old.timestamp(), old.timestamp()))
    assert cache_is_fresh(str(f)) is False

def test_cache_missing_file_is_stale(tmp_path):
    assert cache_is_fresh(str(tmp_path / "nope.html")) is False
