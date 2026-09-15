"""
实验0913-2 独立裁判。

⚠️ 本文件的真值规则【只用于判分】，永不进入提示词、永不提供给 Agent。

判分口径（见 实验设计.md §5）：
  单站通过 = list_pages_fetched >= 3  AND  later_page_unique_urls >= 5
  其中 later_page_unique_urls = Agent 抽到的 URL 中，属于"第2页及以后独有"的数量

真值怎么来：裁判自己按站点规则重抓第 1~N 页，算出每页的真实详情 URL 集合。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Optional
from urllib.parse import urljoin, urlparse, urlunparse

import httpx

BASE_DIR = Path(__file__).resolve().parent

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
HTTP_TIMEOUT = 25.0
MAX_PAGES = 8
REQUEST_INTERVAL = 0.3

# ---------------------------------------------------------------- 真值规则
# 每站：入口页 + 翻页 URL 生成器 + 详情 URL 判定正则
# ⚠️ 仅裁判可见

def _pingan_pager(n: int) -> str:
    return f"http://bank.pingan.com/about/news/index_{n}.shtml"

def _xinlong_pager(n: int) -> str:
    return f"https://www.xinlong-holding.com/news.php?catid=93&page={n}"

def _heryi_pager(n: int) -> str:
    return f"http://www.heryipharma.com/news?&p={n}"

def _huailing_pager(n: int) -> str:
    return f"https://www.sinoictest.com.cn/news/class/?{n}.html"

def _huailing_pager_alt(n: int) -> str:
    """华岭的第二条等价翻页路径（页面上的页码链接指向它）。"""
    return ("https://www.sinoictest.com.cn/news/class/index.php?"
            f"1.html&page={n}&showtj=0&showhot=0&author=&key=")

TRUTH: dict[str, dict[str, Any]] = {
    "000001": {
        "entry": "http://bank.pingan.com/bankPingAnCom/about/news",
        "pager": _pingan_pager,
        # 详情：/about/news/<数字>.shtml  （列表页是 /about/news/ 与 /about/news/index_N.shtml）
        "detail_re": re.compile(r"^/about/news/\d+\.shtml$", re.I),
    },
    "000955": {
        "entry": "https://www.xinlong-holding.com/news.php?catid=93",
        "pager": _xinlong_pager,
        # 详情形态：newsxx.php?catid=93&id=NN  （注意是 newsxx，不是 news.php）
        # 列表页是 news.php?catid=93[&page=N]
        "detail_re": re.compile(r"^/newsxx\.php\?.*\bid=\d+", re.I),
    },
    "920478": {
        "entry": "http://www.heryipharma.com/news",
        "pager": _heryi_pager,
        "detail_re": re.compile(r"^/news_detail/id/\d+\.html$", re.I),
    },
    "920139": {
        "entry": "https://www.sinoictest.com.cn/news/class/?1.html",
        "pager": _huailing_pager,
        # 该站有【两条】等价翻页路径，判分需取并集（见 later_only_vs_page1 说明）
        "pagers": [_huailing_pager, _huailing_pager_alt],
        # ⚠️ 列表页是 /news/class/?N.html；详情页是 /news/html/?N.html
        # 注意 query 里没有等号（`?109.html`），urlparse 会把 "109.html" 当 query。
        # 因此这里匹配 path+query 的拼接，且要求 path 为 /news/html/ 或 /news/html。
        "detail_re": re.compile(r"^/news/html/?\?\d+\.html$", re.I),
    },
    "600486": {
        # 通道对照组：列表 Ajax 渲染，服务端第2页无新链。真值即"无法翻页"
        "entry": "https://www.yangnongchem.com/yangnongchem/xwzx/hyzx/A158004001Gone1.html",
        "pager": lambda n: f"https://www.yangnongchem.com/yangnongchem/xwzx/hyzx/A158004001Gone{n}.html",
        "detail_re": re.compile(r"^/yangnongchem/xwzx/hyzx/\d{4}/\d+/I\d+\.html$", re.I),
    },
    "300582": {
        # 列表页是 /news_company/N.html；详情页实测为 /news_info/<cat>/<id>.html
        # （初版误写为 /news/<id>/<p>.html，导致 160 条真实 URL 被全判为噪声）
        "entry": "https://cn.inventronics-co.com/news_company/1.html",
        "pager": lambda n: f"https://cn.inventronics-co.com/news_company/{n}.html",
        "detail_re": re.compile(r"^/news_info/\d+/\d+\.html$", re.I),
    },
}


# ---------------------------------------------------------------- 抓取/解析

def normalize_url(url: str) -> str:
    """
    规范化 URL：小写域名、去 fragment、去多余尾斜杠（保留 query）。

    仅当没有 query 时才去尾斜杠 —— 否则 `/news/html/?109.html` 会被破坏成
    `/news/html?109.html`（见 运行说明.md 陷阱 4）。
    """
    p = urlparse(url.strip())
    path = p.path or "/"
    if not p.query and path.endswith("/") and len(path) > 1:
        path = path[:-1]
    return urlunparse((p.scheme, p.netloc.lower(), path, "", p.query, ""))


def _key(url: str) -> str:
    """
    比较用键：忽略 http/https、忽略"path 尾斜杠 + query"的歧义写法。

    有些站点把 query 当路径用（如 `/news/html/?109.html`），
    早期版本的去尾斜杠会把它写成 `/news/html?109.html`。
    两者指向同一页面，故归一化为 `/news/html/?109.html` 形式。
    """
    p = urlparse(normalize_url(url))
    path = p.path or "/"
    if p.query and not path.endswith("/"):
        # path + query 拼起来才是一个完整"伪路径"时，补回斜杠
        path = path + "/"
    return f"{p.netloc.lower()}{path}{('?' + p.query) if p.query else ''}"


def fetch(url: str) -> tuple[Optional[str], str, int, Optional[str]]:
    """抓取页面。"""
    try:
        with httpx.Client(timeout=HTTP_TIMEOUT, follow_redirects=True,
                          headers={"User-Agent": USER_AGENT,
                                   "Accept-Language": "zh-CN,zh;q=0.9"}) as c:
            r = c.get(url)
            if r.status_code != 200:
                return None, str(r.url), r.status_code, f"HTTP {r.status_code}"
            return r.text, str(r.url), r.status_code, None
    except Exception as e:
        return None, url, 0, f"{type(e).__name__}: {e}"


def detail_urls_from(html: str, page_url: str, pattern: re.Pattern) -> set[str]:
    """按站点正则从页面抽详情 URL。"""
    host = urlparse(page_url).netloc.lower()
    out: set[str] = set()
    for href in re.findall(r'href=["\']([^"\']+)["\']', html, re.I):
        # HTML 实体解码：源站大量使用 &amp; 连接 query 参数
        href = (href.replace("&amp;", "&").replace("&#39;", "'")
                    .replace("&quot;", '"').replace("&nbsp;", " "))
        abs_url = urljoin(page_url, href)
        p = urlparse(abs_url)
        if p.netloc.lower() != host:
            continue
        if pattern.search(p.path + (("?" + p.query) if p.query else "")):
            out.add(_key(abs_url))
    return out


def truth_for(code: str, max_pages: int = MAX_PAGES) -> dict[str, Any]:
    """
    裁判真值：抓入口页 + 后续页，算出每页详情 URL 与"后续页独有"集合。

    Returns:
        {per_page: [set, ...], page1: set, later_only: set, errors: [...]}
    """
    cfg = TRUTH[code]
    per_page: list[set[str]] = []
    errors: list[str] = []
    for i in range(1, max_pages + 1):
        url = cfg["entry"] if i == 1 else cfg["pager"](i)
        html, final_url, status, err = fetch(url)
        if err or not html:
            errors.append(f"第{i}页抓取失败 {url}: {err}")
            break
        per_page.append(detail_urls_from(html, final_url, cfg["detail_re"]))
        # 若某页为空或与首页完全相同且是通道对照组，提前停
    page1 = per_page[0] if per_page else set()
    later = set().union(*per_page[1:]) if len(per_page) > 1 else set()
    return {
        "per_page": per_page,
        "page1": page1,
        "later_only": later - page1,
        "errors": errors,
    }


def later_only_vs_page1(code: str) -> set[str]:
    """
    真值：「不在入口页上」的详情 URL 全集。

    ⚠️ 为什么不能只用 truth_for().later_only：
    同一站可能有【多条等价的翻页路径】（如 华岭股份 既有 /news/class/?2.html，
    也有 /news/class/index.php?...page=2），两条路径返回不同内容。
    Agent 走哪条都合法。若裁判只按其中一条算 later_only，
    走另一条的 Agent 会被误判为 0（实测 华岭 24 条真实新 URL 被误判）。

    本函数枚举所有已知翻页路径，取并集后减去入口页 —— 与 Agent 走哪条路径无关。
    """
    cfg = TRUTH[code]
    page1_raw = fetch(cfg["entry"])
    page1: set[str] = set()
    if page1_raw[0]:
        page1 = detail_urls_from(page1_raw[0], page1_raw[1], cfg["detail_re"])

    union: set[str] = set()
    for n in range(2, MAX_PAGES + 1):
        for make_url in cfg.get("pagers", [cfg["pager"]]):
            html, final_url, status, err = fetch(make_url(n))
            if err or not html:
                continue
            union |= detail_urls_from(html, final_url, cfg["detail_re"])
    return union - page1


# ---------------------------------------------------------------- 判分

def judge_run(code: str, run_dir: Path) -> dict[str, Any]:
    """
    对一次 run 判分。

    Args:
        code: 股票代码
        run_dir: 该次 run 的输出目录（含 news_urls.json）

    Returns:
        判分结果
    """
    news_json = run_dir / "news_urls.json"
    if not news_json.exists():
        return {"code": code, "run": run_dir.name, "passed": False,
                "reason": "news_urls.json 不存在（Agent 未调用 save_results？）"}

    payload = json.loads(news_json.read_text(encoding="utf-8"))
    agent_urls = [_key(u) for u in
                  {i["url"] for page in payload.get("pages", []) for i in page.get("news", [])}]
    agent_set = set(agent_urls)

    t = truth_for(code, max_pages=MAX_PAGES)
    # ⚠️ 用「与翻页路径无关」的口径算 later_only（见 later_only_vs_page1）
    page1 = t["page1"]
    later_only = later_only_vs_page1(code)
    t["errors"] = t["errors"]

    hit_page1 = agent_set & page1
    hit_later = agent_set & later_only
    noise = agent_set - page1 - later_only

    run_meta = {}
    meta_path = run_dir / "run_meta.json"
    if meta_path.exists():
        run_meta = json.loads(meta_path.read_text(encoding="utf-8"))

    list_pages = payload.get("list_pages") or []
    # 有效列表页：去掉重复 final_url
    seen_pages, uniq_pages = set(), []
    for p in list_pages:
        k = normalize_url(p.get("final_url") or p.get("requested_url") or "")
        if k and k not in seen_pages:
            seen_pages.add(k)
            uniq_pages.append(k)

    pages_ok = len(uniq_pages) >= 3
    later_ok = len(hit_later) >= 5
    passed = bool(pages_ok and later_ok)

    return {
        "code": code,
        "company_name": payload.get("company_name", ""),
        "run": run_dir.name,
        "passed": passed,
        "pages_ok": pages_ok,
        "later_ok": later_ok,
        # 核心指标
        "list_pages_fetched": len(uniq_pages),
        "list_page_urls": uniq_pages,
        "agent_url_count": len(agent_set),
        "hit_page1": len(hit_page1),
        "truth_page1_count": len(page1),
        "later_page_unique_urls": len(hit_later),
        "truth_later_only_count": len(later_only),
        "hit_rate": round(len(agent_set & (page1 | later_only)) / len(agent_set), 3) if agent_set else 0.0,
        "recall_later": round(len(hit_later) / len(later_only), 3) if later_only else None,
        "noise_count": len(noise),
        # 成本
        "agent_turns": (run_meta.get("agent") or {}).get("turns"),
        "cost_usd": (run_meta.get("agent") or {}).get("cost_usd"),
        "agent_is_error": (run_meta.get("agent") or {}).get("is_error"),
        "tool_errors": len(run_meta.get("errors") or []),
        # 真值抓取问题（环境/改版，不算 Agent 的错）
        "truth_errors": t["errors"],
        "reason": ("通过" if passed else
                   ("页数不足(%d<3)" % len(uniq_pages) if not pages_ok else
                    "后续页新URL不足(%d<5)" % len(hit_later))),
    }


def main() -> int:
    """CLI：判分某个 run 目录。"""
    if len(sys.argv) < 3:
        print("用法: python judge.py <stock_code> <run_dir>")
        return 2
    result = judge_run(sys.argv[1], Path(sys.argv[2]))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result.get("passed") else 1


if __name__ == "__main__":
    sys.exit(main())
