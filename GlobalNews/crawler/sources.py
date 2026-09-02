# -*- coding: utf-8 -*-
"""RSS 源配置 — v2 权威源列表。category 直接写死，不再靠名称猜。"""

PROXY_SOURCES_HINT = "needs_proxy=True 的源走 config.json 的代理"

RSS_SOURCES = [
    # ---- world 国际形势 ----
    {"name": "BBC World",            "url": "https://feeds.bbci.co.uk/news/world/rss.xml",        "category": "world",   "weight": 3, "needs_proxy": True},
    {"name": "Guardian World",       "url": "https://www.theguardian.com/world/rss",              "category": "world",   "weight": 3, "needs_proxy": True},
    {"name": "NYT World",            "url": "https://rss.nytimes.com/services/xml/rss/nyt/World.xml", "category": "world", "weight": 3, "needs_proxy": True},
    # UN News 旧 feed 路径 /feed/section/en/... 已失效（HTTP 200 但 0 条），2026-09-02 换为官方新路径
    {"name": "UN News",              "url": "https://news.un.org/feed/subscribe/en/news/topic/peace-and-security/feed/rss.xml", "category": "world", "weight": 2, "needs_proxy": True},
    {"name": "China Daily World",    "url": "https://www.chinadaily.com.cn/rss/world_rss.xml",    "category": "world",   "weight": 1, "needs_proxy": False},
    # ---- science 前沿科研 ----
    {"name": "Nature",               "url": "https://www.nature.com/nature.rss",                  "category": "science", "weight": 3, "needs_proxy": True},
    {"name": "Science",              "url": "https://www.science.org/action/showFeed?jc=science&type=etoc&feed=rss", "category": "science", "weight": 3, "needs_proxy": True},
    {"name": "WHO News",             "url": "https://www.who.int/rss-feeds/news-english.xml",     "category": "science", "weight": 2, "needs_proxy": True},
    # NIH News: 代理与直连均 403（Akamai 反爬，备用路径亦 403），2026-09-02 移除
    # {"name": "NIH News",             "url": "https://www.nih.gov/news-events/news-releases/feed", "category": "science", "weight": 2, "needs_proxy": True},
    {"name": "ScienceDaily Chem",    "url": "https://www.sciencedaily.com/rss/matter_energy/chemistry.xml", "category": "science", "weight": 1, "needs_proxy": False},
    {"name": "ScienceDaily Bio",     "url": "https://www.sciencedaily.com/rss/plants_animals/biology.xml", "category": "science", "weight": 1, "needs_proxy": False},
    {"name": "ScienceDaily Mat",     "url": "https://www.sciencedaily.com/rss/matter_energy/materials_science.xml", "category": "science", "weight": 1, "needs_proxy": False},
    {"name": "Phys.org Chem",        "url": "https://phys.org/rss-feed/chemistry-news/",         "category": "science", "weight": 1, "needs_proxy": False},
    {"name": "Phys.org Bio",         "url": "https://phys.org/rss-feed/biology-news/",           "category": "science", "weight": 1, "needs_proxy": False},
    # JACS (ACS): 代理与直连均 403（ACS 反爬，feed 参数变体亦 403），2026-09-02 移除
    # {"name": "JACS (ACS)",           "url": "https://pubs.acs.org/action/showFeed?type=etoc&feed=rss&jc=jacsat", "category": "science", "weight": 2, "needs_proxy": True},
    # Angew. Chem.: 旧期刊 ID 15212665 已 404，2026-09-02 换为 Int. Ed. 正确 ID 15213773
    {"name": "Angew. Chem.",         "url": "https://onlinelibrary.wiley.com/feed/15213773/most-recent", "category": "science", "weight": 2, "needs_proxy": True},
    {"name": "Adv. Mater.",          "url": "https://onlinelibrary.wiley.com/feed/15214095/most-recent", "category": "science", "weight": 2, "needs_proxy": True},
    {"name": "Cell (in press)",      "url": "https://www.cell.com/cell/inpress.rss",             "category": "science", "weight": 2, "needs_proxy": True},
    # ---- ai AI 成果 ----
    {"name": "arXiv cs.AI",          "url": "https://rss.arxiv.org/rss/cs.AI",                   "category": "ai",      "weight": 3, "needs_proxy": False},
    {"name": "arXiv cs.CL",          "url": "https://rss.arxiv.org/rss/cs.CL",                   "category": "ai",      "weight": 3, "needs_proxy": False},
    {"name": "arXiv cs.LG",          "url": "https://rss.arxiv.org/rss/cs.LG",                   "category": "ai",      "weight": 3, "needs_proxy": False},
    {"name": "MIT Tech Review AI",   "url": "https://www.technologyreview.com/topic/artificial-intelligence/feed", "category": "ai", "weight": 2, "needs_proxy": True},
    # 机器之心: RSS 已停服（/rss.xml 返回"数据服务"推广页，需申请开通），2026-09-02 移除
    # {"name": "机器之心",             "url": "https://www.jiqizhixin.com/rss.xml",                "category": "ai",      "weight": 1, "needs_proxy": False},
]

CATEGORY_LABELS = {"world": "国际形势", "science": "前沿科研", "ai": "AI 成果"}

def auto_tag(source_name: str) -> str:
    """兜底：按名称猜分类，仅在源未配置 category 时使用。"""
    n = source_name.lower()
    if any(k in n for k in ["bbc", "guardian", "nyt", "un news", "china daily", "xinhua"]):
        return "world"
    if any(k in n for k in ["nature", "science", "who", "nih", "sciencedaily", "phys.org", "acs", "wiley", "cell"]):
        return "science"
    if any(k in n for k in ["arxiv", "tech review", "机器之心"]):
        return "ai"
    return "science"
