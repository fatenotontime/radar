# -*- coding: utf-8 -*-
from crawler import pipeline

def _e(id, title, link, date):
    return {"id": id, "title": title, "link": link, "summary": "s",
            "title_zh": "", "summary_zh": "", "source": "S", "category": "ai",
            "published": date, "added_date": date, "possible_duplicate": False}

def test_url_dedup_and_keep_history(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DATA_FILE", str(tmp_path / "d.json"))
    e1 = [_e("a", "T1", "http://x/1", "2026-09-01")]
    assert len(pipeline.merge_data(e1)) == 1
    # 同 URL 再来不重复计数；新 URL 保留旧+新（全量保留，无上限）
    e2 = e1 + [_e("b", "T2", "http://x/2", "2026-09-02")]
    assert len(pipeline.merge_data(e2)) == 2

def test_title_similar_marks_possible_duplicate(tmp_path, monkeypatch):
    monkeypatch.setattr(pipeline, "DATA_FILE", str(tmp_path / "d.json"))
    e1 = [_e("a", "New CRISPR study published", "http://x/1", "2026-09-01")]
    pipeline.merge_data(e1)
    e2 = [_e("b", "New CRISPR study published", "http://x/2", "2026-09-02")]
    out = pipeline.merge_data(e2)
    dup = [x for x in out if x["id"] == "b"]
    assert dup and dup[0]["possible_duplicate"] is True

def test_monthly_cleanup_gone(tmp_path, monkeypatch):
    # 全量保留：老条目不被清理
    monkeypatch.setattr(pipeline, "DATA_FILE", str(tmp_path / "d.json"))
    old = [_e("a", "T1", "http://x/1", "2020-01-01")]
    pipeline.merge_data(old)
    e2 = old + [_e("b", "T2", "http://x/2", "2026-09-02")]
    out = pipeline.merge_data(e2)
    assert len(out) == 2  # 2020 年的也在
