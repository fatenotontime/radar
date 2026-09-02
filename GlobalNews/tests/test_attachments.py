# -*- coding: utf-8 -*-
"""附件归档测试：mock requests 层（假 session），不碰真实网络。"""
import os
from datetime import datetime

from crawler import attachments as att


class _FakeResp:
    """GET 响应假件。"""
    def __init__(self, content=b"%PDF-1.4 fake"):
        self.content = content
        self.status_code = 200

    def raise_for_status(self):
        pass


class _FakeHead:
    """HEAD 响应假件：headers 可含 Content-Length。"""
    def __init__(self, content_length=None):
        self.headers = {}
        if content_length is not None:
            self.headers["Content-Length"] = str(content_length)


class _FakeSession:
    """替换 build_session 的假会话，记录 GET 调用与 close 供断言。"""
    def __init__(self, head=None, get_resp=None):
        self._head = head if head is not None else _FakeHead()
        self._get = get_resp if get_resp is not None else _FakeResp()
        self.get_calls = []
        self.closed = False

    def head(self, url, timeout=15, allow_redirects=True):
        return self._head

    def get(self, url, timeout=60):
        self.get_calls.append(url)
        return self._get

    def close(self):
        self.closed = True


def _patch(monkeypatch, tmp_path, session, cfg=None):
    """统一 mock：附件目录 / 配置 / 代理判定 / 会话工厂 / 限速 sleep。"""
    monkeypatch.setattr(att, "ATTACH_DIR", str(tmp_path))
    monkeypatch.setattr(att, "load_config",
                        lambda: cfg if cfg is not None else {"attachment": {"max_mb": 20}})
    monkeypatch.setattr(att, "_source_needs_proxy", lambda name: False)
    monkeypatch.setattr(att, "build_session", lambda np, p: session)
    monkeypatch.setattr(att.time, "sleep", lambda *_: None)
    return session


def test_filename_from_url():
    assert att._filename_from_url("https://arxiv.org/pdf/2609.00002v1") == "2609.00002v1.pdf"
    assert att._filename_from_url("https://x.org/report/abc.pdf?download=1") == "abc.pdf"
    # 无 .pdf 的 URL 兜底
    assert att._filename_from_url("https://x.org/whatever") == "file.pdf"


def test_download_saves_and_caps(tmp_path, monkeypatch):
    url = "https://arxiv.org/pdf/2609.00002v1"
    entry = {"source": "arXiv cs.AI", "detail": {"pdf_links": [url]}}
    s = _patch(monkeypatch, tmp_path, _FakeSession(head=_FakeHead(18)))

    saved = att.download_all(entry, "")

    month = datetime.now().strftime("%Y-%m")
    fpath = os.path.join(str(tmp_path), month, "2609.00002v1.pdf")
    assert os.path.isfile(fpath)
    with open(fpath, "rb") as f:
        assert f.read() == b"%PDF-1.4 fake"
    assert saved == [{"filename": "2609.00002v1.pdf", "size": 13, "url": url}]
    assert s.get_calls == [url]
    assert s.closed is True


def test_download_skips_oversized(tmp_path, monkeypatch):
    url = "https://arxiv.org/pdf/2609.00002v1"
    entry = {"source": "arXiv cs.AI", "detail": {"pdf_links": [url]}}
    s = _patch(monkeypatch, tmp_path, _FakeSession(head=_FakeHead(21 * 1024 * 1024)))

    saved = att.download_all(entry, "")

    assert saved == []
    assert s.get_calls == []  # 超限：HEAD 后即跳过，未发起 GET
    month_dir = os.path.join(str(tmp_path), datetime.now().strftime("%Y-%m"))
    assert not os.path.exists(month_dir)


def test_download_empty_links_no_error(tmp_path, monkeypatch):
    _patch(monkeypatch, tmp_path, _FakeSession())
    # detail 缺失 / detail 无 pdf_links / pdf_links 为空 → 均返回 [] 不抛异常
    assert att.download_all({"source": "arXiv cs.AI"}) == []
    assert att.download_all({"source": "arXiv cs.AI", "detail": {}}) == []
    assert att.download_all({"source": "arXiv cs.AI", "detail": {"pdf_links": []}}) == []


def test_download_disabled_by_config(tmp_path, monkeypatch):
    entry = {"source": "arXiv cs.AI", "detail": {"pdf_links": ["https://arxiv.org/pdf/2609.00002v1"]}}
    s = _patch(monkeypatch, tmp_path, _FakeSession(),
               cfg={"attachment": {"enabled": False, "max_mb": 20}})
    assert att.download_all(entry, "") == []
    assert s.get_calls == []
