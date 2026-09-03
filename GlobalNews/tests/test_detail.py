# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
from crawler.detail import select_for_detail, cache_is_fresh, extract_pdf_links

def test_extract_pdf_links_resolves_relative():
    # nature.com 等站点用相对路径 href，应按页面 URL 解析为绝对地址
    html = '<a href="/articles/s41586-026-10982-x.pdf">PDF</a>'
    links = extract_pdf_links(html, "https://www.nature.com/articles/s41586-026-10982-x")
    assert links == ["https://www.nature.com/articles/s41586-026-10982-x.pdf"]

def test_extract_pdf_links_keeps_absolute_and_dedup():
    html = ('<a href="https://a.org/p1.pdf">1</a>'
            '<a href="https://a.org/p1.pdf">dup</a>'
            '<a href="https://b.org/p2.pdf?x=1">2</a>')
    links = extract_pdf_links(html, "https://c.org/page")
    assert links == ["https://a.org/p1.pdf", "https://b.org/p2.pdf?x=1"]

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
