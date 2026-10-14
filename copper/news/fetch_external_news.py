# -*- coding: utf-8 -*-
"""
抓取 10 个外部资讯网站上与 铜 / 金 / 银 / 铝 相关的新闻标题、摘要和链接，
保存到 external_news.json（只存标题、网站自己给出的一两句摘要、发布日期和原文链接，不存正文）。

来源:
    Mining.com · Mining Weekly · The Northern Miner · MetalMiner · Kitco News · BullionVault ·
    世界黄金协会(Gold Focus) · Silver Institute · AlCircle · Aluminium International Today

用法:
    python fetch_external_news.py            抓取并合并进 external_news.json
    然后 python build_cu_smelter_refinery.py   把资讯并入网页的"外部综合资讯"栏目
    python fetch_external_news.py --page-json ../ext_news.json
        抓取后另外写一份网页直接读取的精简数据（线上仓库的 GitHub Actions 用这个；
        网页上的"更新资讯"按钮触发的就是它，不需要重新生成整个网页）
    --data-dir DIR    external_news.json 和已读链接清单改放到 DIR 里（线上用：数据单独放在一个分支）

说明:
    - 有 RSS 的网站读 RSS；没有的读新闻列表页，再逐篇读文章页的 meta 描述和发布时间
    - 已抓过的链接不会重复请求；中文标题/摘要(zh_title, zh_summary)在 external_news_zh.json 里另存
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin

PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
STORE = os.path.join(PROJECT_DIR, "external_news.json")
ZH_STORE = os.path.join(PROJECT_DIR, "external_news_zh.json")   # 中文精炼（标题 + 一句话摘要）
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/126.0 Safari/537.36")
MAX_NEW_PER_SITE = 40     # 没有 RSS 的网站，每次最多新读这么多篇文章页
DELAY = 0.4               # 两次请求之间的间隔（秒）

METALS = {
    "铜": re.compile(r"\bcopper\b|\bcu\b(?=[ -]?(?:mine|concentrate))|\bcodelco\b|\bcathode", re.I),
    "金": re.compile(r"\bgold\b|\bbullion\b", re.I),
    "银": re.compile(r"\bsilver\b", re.I),
    "铝": re.compile(r"\balumin(?:i)?um\b|\bbauxite\b|\balumina\b|\bsmelter grade\b", re.I),
}
# 站点本身只讲某一个品种的，关键词没命中时归到这个品种
SITE_DEFAULT = {"AlCircle": "铝", "Aluminium International Today": "铝", "Silver Institute": "银",
                "世界黄金协会": "金"}


def get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


def clean(s):
    s = re.sub(r"<[^>]+>", " ", s or "")
    return re.sub(r"\s+", " ", html.unescape(html.unescape(s))).strip()


def iso_date(s):
    """各种日期写法 -> YYYY-MM-DD；认不出来返回空串。"""
    s = (s or "").strip()
    if not s:
        return ""
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return m.group(0)
    try:
        return parsedate_to_datetime(s).strftime("%Y-%m-%d")
    except Exception:
        pass
    s2 = re.sub(r"(\d)(st|nd|rd|th)\b", r"\1", s).replace(",", "")
    for fmt in ("%d %B %Y", "%d %b %Y", "%b %d %Y", "%B %d %Y"):
        try:
            return datetime.strptime(s2.title(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return ""


# ---------------------------------------------------------------- RSS
def from_rss(site, url):
    root = ET.fromstring(get(url).encode("utf-8"))
    out = []
    for it in root.iter("item"):
        g = lambda tag: (it.findtext(tag) or "").strip()
        desc = clean(g("description"))
        desc = re.sub(r"\s*(The post .* appeared first on .*|\[…\]|\[&#8230;\]|Read more.*)$", "", desc).strip()
        out.append({"site": site, "url": g("link"), "title": clean(g("title")), "desc": desc[:400],
                    "date": iso_date(g("pubDate"))})
    return out


# ---------------------------------------------------------------- 列表页 + 文章页
def article_meta(url):
    """读文章页的 og:title / description / 发布时间。"""
    s = get(url)
    meta = lambda pat: (re.search(pat, s, re.I | re.S) or [None, ""])[1]
    title = meta(r'<meta[^>]+property="og:title"[^>]+content="([^"]*)"') or \
        meta(r'<meta[^>]+content="([^"]*)"[^>]+property="og:title"') or meta(r"<title>(.*?)</title>")
    desc = meta(r'<meta[^>]+name="description"[^>]+content="([^"]*)"') or \
        meta(r'<meta[^>]+content="([^"]*)"[^>]+(?:name="description"|property="og:description")') or \
        meta(r'<meta[^>]+property="og:description"[^>]+content="([^"]*)"')
    date = meta(r'"datePublished"\s*:\s*"([^"]+)"') or \
        meta(r'<meta[^>]+property="article:published_time"[^>]+content="([^"]*)"') or \
        meta(r'<time[^>]+datetime="([^"]+)"')
    return clean(title), clean(desc)[:400], iso_date(date)


def from_listing(site, pages, link_re, known, date_from_url=None, title_fix=None):
    """pages: 列表页 URL；link_re: 文章链接的正则；known: 已抓过的 url 集合。"""
    urls = []
    for page in pages:
        try:
            s = get(page)
        except Exception as e:  # noqa: BLE001
            print(f"   [跳过] {page}: {e}")
            continue
        for href in re.findall(link_re, s):
            u = urljoin(page, html.unescape(href))
            if u not in urls:
                urls.append(u)
        time.sleep(DELAY)
    out, fetched = [], 0
    for u in urls:
        if u in known:
            continue
        if fetched >= MAX_NEW_PER_SITE:
            break
        try:
            title, desc, date = article_meta(u)
        except Exception as e:  # noqa: BLE001
            print(f"   [跳过] {u}: {e}")
            continue
        fetched += 1
        if date_from_url and not date:
            date = date_from_url(u)
        if title_fix:
            title = title_fix(title)
        out.append({"site": site, "url": u, "title": title, "desc": desc, "date": date})
        time.sleep(DELAY)
    return out


def _bv_date(u):   # BullionVault 链接末尾是 MMDDYYYY 加一位序号
    m = re.search(r"(\d{2})(\d{2})(\d{4})\d$", u)
    return f"{m.group(3)}-{m.group(1)}-{m.group(2)}" if m else ""


def _url_date(u):
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", u)
    return m.group(0) if m else ""


_strip_site = lambda t: re.sub(r"\s*[|\-–]\s*(Kitco News|KITCO|BullionVault|Mining Weekly|AlCircle|AL Circle|"
                               r"Aluminium International Today|World Gold Council|Gold Focus blog).*$", "", t).strip()


def collect(known):
    jobs = [
        ("Mining.com", lambda: sum((from_rss("Mining.com", f"https://www.mining.com/commodity/{c}/feed/")
                                    for c in ("copper", "gold", "silver", "aluminum")), [])),
        ("The Northern Miner", lambda: from_rss("The Northern Miner", "https://www.northernminer.com/feed/")),
        ("MetalMiner", lambda: from_rss("MetalMiner", "https://agmetalminer.com/feed/")),
        ("Silver Institute", lambda: from_rss("Silver Institute", "https://silverinstitute.org/feed/")),
        ("Mining Weekly", lambda: from_listing(
            "Mining Weekly", ["https://www.miningweekly.com/", "https://www.miningweekly.com/page/base-metals",
                              "https://www.miningweekly.com/page/gold"],
            r'href="(/article/[^"]+-\d{4}-\d{2}-\d{2})"', known, _url_date, _strip_site)),
        ("Kitco News", lambda: from_listing(
            "Kitco News", ["https://www.kitco.com/news/category/mining", "https://www.kitco.com/news/category/commodities",
                           "https://www.kitco.com/news/"],
            r'href="(/news/(?:article|off-the-wire)/\d{4}-\d{2}-\d{2}/[^"]+)"', known, _url_date, _strip_site)),
        ("BullionVault", lambda: from_listing(
            "BullionVault", ["https://www.bullionvault.com/gold-news"],
            r'href="(https://www\.bullionvault\.com/gold-news/[^"]+\d{9})"', known, _bv_date, _strip_site)),
        ("世界黄金协会", lambda: from_listing(
            "世界黄金协会", ["https://www.gold.org/goldhub/gold-focus"],
            r'href="(/goldhub/gold-focus/\d{4}/\d{2}/[a-z0-9][^"/]+)"', known,
            lambda u: (re.search(r"/(\d{4})/(\d{2})/", u) and "-".join(re.search(r"/(\d{4})/(\d{2})/", u).groups()) + "-01") or "",
            _strip_site)),
        ("AlCircle", lambda: from_listing(
            "AlCircle", ["https://www.alcircle.com/news"],
            r'href="(/news/(?!events/)[a-z0-9][^"/]*-\d{4,})"', known, None, _strip_site)),
        ("Aluminium International Today", lambda: from_listing(
            "Aluminium International Today", ["https://aluminiumtoday.com/news"],
            r'href="(https://aluminiumtoday\.com/news/[a-z0-9][^"/]+)"', known, None, _strip_site)),
    ]
    items = []
    for name, job in jobs:
        try:
            got = job()
            print(f"[{name}] 取到 {len(got)} 条")
            items.extend(got)
        except Exception as e:  # noqa: BLE001
            print(f"[{name}] 失败：{e}")
    return items


def tag_metals(it):
    text = it["title"] + " " + it["desc"]
    metals = [m for m, rx in METALS.items() if rx.search(text)]
    if not metals and it["site"] in SITE_DEFAULT:
        metals = [SITE_DEFAULT[it["site"]]]
    return metals


def page_items():
    """网页用的精简格式：有中文精炼的用中文，没有的保留英文原题和网站自带摘要。"""
    if not os.path.exists(STORE):
        return []
    with open(STORE, encoding="utf-8") as f:
        rows = json.load(f)
    zh = {}
    if os.path.exists(ZH_STORE):
        with open(ZH_STORE, encoding="utf-8") as f:
            zh = json.load(f)
    out, seen = [], set()
    for r in rows:
        z = zh.get(r["id"]) or {}
        if z.get("hide") or r["title"].strip().lower() == r["site"].lower() or r["title"].lower().startswith("sponsored"):
            continue
        key = (r["site"], r["title"])
        if key in seen:
            continue
        seen.add(key)
        item = {"d": r["date"], "site": r["site"], "u": r["url"], "m": r["metals"], "en": r["title"]}
        if z.get("t"):
            item.update({"t": z["t"], "s": z.get("s", "")})
        else:
            item.update({"t": r["title"], "s": r["desc"], "raw": 1})
        out.append(item)
    return out


def main():
    global STORE
    seen_path = os.path.join(PROJECT_DIR, "atlas_data", "external_news_seen.json")
    if "--data-dir" in sys.argv:
        data_dir = os.path.abspath(sys.argv[sys.argv.index("--data-dir") + 1])
        STORE = os.path.join(data_dir, "external_news.json")
        seen_path = os.path.join(data_dir, "external_news_seen.json")
    store = []
    if os.path.exists(STORE):
        with open(STORE, encoding="utf-8") as f:
            store = json.load(f)
    by_url = {r["url"]: r for r in store}
    seen = set(by_url)
    if os.path.exists(seen_path):          # 读过但与四个品种无关的链接也记下来，下次不再请求
        with open(seen_path, encoding="utf-8") as f:
            seen |= set(json.load(f))

    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    added = 0
    for it in collect(seen):
        if not it["url"] or not it["title"]:
            continue
        if it["title"].strip().lower() == it["site"].lower() or it["title"].lower().startswith("sponsored"):
            seen.add(it["url"])      # 栏目首页之类的通用页、赞助内容
            continue
        seen.add(it["url"])
        if it["url"] in by_url:
            continue
        metals = tag_metals(it)
        if not metals:
            continue
        it.update({"id": hashlib.md5(it["url"].encode()).hexdigest()[:12], "metals": metals,
                   "date": it["date"] or today, "fetched": today})
        by_url[it["url"]] = it
        added += 1

    # 抓到过的资讯一直保留在本地文件里，只增不删
    rows = sorted(by_url.values(), key=lambda r: r["date"], reverse=True)
    tmp = STORE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(rows, f, ensure_ascii=False, indent=1)
    os.replace(tmp, STORE)       # 先写临时文件再替换，中途出错不会把已有数据写坏
    os.makedirs(os.path.dirname(seen_path), exist_ok=True)
    with open(seen_path, "w", encoding="utf-8") as f:
        json.dump(sorted(seen), f)

    from collections import Counter
    print(f"\n新增 {added} 条，文件里累计 {len(rows)} 条（只增不删）-> {STORE}")
    print("按网站：", dict(Counter(r["site"] for r in rows)))
    print("按品种：", dict(Counter(m for r in rows for m in r["metals"])))
    if rows:
        print("日期范围：", rows[-1]["date"], "~", rows[0]["date"])

    if "--page-json" in sys.argv:
        path = os.path.abspath(sys.argv[sys.argv.index("--page-json") + 1])
        items = page_items()
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "items": items},
                      f, ensure_ascii=False, separators=(",", ":"))
        print(f"网页数据 {len(items)} 条 -> {path}")


if __name__ == "__main__":
    sys.exit(main())
