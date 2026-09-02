# -*- coding: utf-8 -*-
from crawler.fetch import build_session

def test_proxy_session_uses_config_proxy():
    s = build_session(needs_proxy=True, proxy="http://127.0.0.1:7993")
    assert s.proxies == {"http": "http://127.0.0.1:7993", "https": "http://127.0.0.1:7993"}

def test_direct_session_has_no_proxy():
    s = build_session(needs_proxy=False, proxy="http://127.0.0.1:7993")
    assert s.proxies == {} and s.trust_env is False
