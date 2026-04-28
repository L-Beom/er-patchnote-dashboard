"""
이터널리턴 패치노트 크롤러
- URL: https://playeternalreturn.com/posts/news?categoryPath=patchnote
- Playwright 기반 (Next.js SPA 대응)
- window.__NEXT_DATA__ → API 인터셉트 → DOM 스크래핑 순서로 시도
"""

import json
import csv
import re
import asyncio
from datetime import datetime
from pathlib import Path

try:
    from playwright.async_api import async_playwright
except ImportError:
    print("Playwright가 설치되어 있지 않습니다.")
    print("설치: pip install playwright && playwright install chromium")
    exit(1)


BASE_URL = "https://playeternalreturn.com"
LIST_URL = f"{BASE_URL}/posts/news?categoryPath=patchnote"
OUTPUT_DIR = Path("er_patchnotes")
OUTPUT_DIR.mkdir(exist_ok=True)


# ─────────────────────────────────────────────
# 유틸
# ─────────────────────────────────────────────

def _nested_get(obj, *keys):
    """중첩 dict/list에서 키 경로로 값 추출"""
    for key in keys:
        if obj is None:
            return None
        if isinstance(obj, list):
            obj = obj[0] if obj else None
        elif isinstance(obj, dict):
            obj = obj.get(key)
    return obj


def _find_in_dict(obj, targets: list[str], _depth=0) -> str | None:
    """dict 전체를 재귀 탐색하여 target 키의 값 반환"""
    if _depth > 10 or not isinstance(obj, (dict, list)):
        return None
    items = obj.items() if isinstance(obj, dict) else enumerate(obj)
    for k, v in items:
        if isinstance(k, str) and k.lower() in targets and isinstance(v, str) and v.strip():
            return v.strip()
        result = _find_in_dict(v, targets, _depth + 1)
        if result:
            return result
    return None


# ─────────────────────────────────────────────
# Next.js __NEXT_DATA__ 파싱
# ─────────────────────────────────────────────

async def extract_next_data(page) -> dict:
    """window.__NEXT_DATA__ 전체를 반환"""
    return await page.evaluate("() => window.__NEXT_DATA__ || null") or {}


def parse_post_from_next_data(data: dict) -> dict:
    """__NEXT_DATA__ 에서 title, date, content 추출"""
    props = data.get("props", {})
    page_props = props.get("pageProps", {})

    # 다양한 키 이름 시도
    post_obj = (
        page_props.get("post")
        or page_props.get("article")
        or page_props.get("newsPost")
        or page_props.get("data")
        or page_props
    )

    title = _find_in_dict(post_obj, ["title", "subject", "name"]) or ""
    date = (
        _find_in_dict(post_obj, ["createdAt", "publishedAt", "date", "regDate", "created_at", "published_at"])
        or ""
    )
    content = (
        _find_in_dict(post_obj, ["content", "body", "html", "contents", "description"])
        or ""
    )
    return {"title": title, "date": date, "content": content}


def parse_list_from_next_data(data: dict) -> list[dict]:
    """__NEXT_DATA__ 에서 게시글 목록 추출"""
    props = data.get("props", {}).get("pageProps", {})

    # 가능한 목록 키 탐색
    for key in ("posts", "articles", "list", "items", "data", "newsList"):
        items = props.get(key)
        if isinstance(items, list) and items:
            return items

    # 재귀 탐색
    def find_list(obj, depth=0):
        if depth > 5:
            return None
        if isinstance(obj, list) and len(obj) > 0 and isinstance(obj[0], dict):
            return obj
        if isinstance(obj, dict):
            for v in obj.values():
                r = find_list(v, depth + 1)
                if r:
                    return r
        return None

    return find_list(props) or []


# ─────────────────────────────────────────────
# API 응답 인터셉터
# ─────────────────────────────────────────────

def make_api_interceptor():
    """API 응답을 캡처하는 핸들러와 저장소를 반환"""
    captured = []

    async def handler(response):
        url = response.url
        if response.status != 200:
            return
        # JSON 응답인 XHR/fetch만 캡처
        ct = response.headers.get("content-type", "")
        if "json" not in ct:
            return
        # Next.js 데이터 라우트 또는 /api/ 경로
        if "/_next/data/" in url or "/api/" in url:
            try:
                body = await response.json()
                captured.append({"url": url, "body": body})
            except Exception:
                pass

    return handler, captured


# ─────────────────────────────────────────────
# DOM 스크래핑 (page.evaluate 기반)
# ─────────────────────────────────────────────

_EXTRACT_DETAIL_JS = """
() => {
    const result = { title: '', date: '', content: '' };

    // ── 제목 ──────────────────────────────────────
    const titleEl = (
        document.querySelector('h1') ||
        document.querySelector('h2') ||
        document.querySelector('[class*="title" i]')
    );
    if (titleEl) result.title = titleEl.innerText.trim();

    // ── 날짜 ─────────────────────────────────────
    // 1) <time datetime="..."> 속성값 우선
    const timeEl = document.querySelector('time[datetime]');
    if (timeEl) {
        result.date = timeEl.getAttribute('datetime') || timeEl.innerText.trim();
    }

    // 2) datetime 없는 <time>
    if (!result.date) {
        const timeEl2 = document.querySelector('time');
        if (timeEl2) result.date = timeEl2.innerText.trim();
    }

    // 3) class에 date/time 포함된 요소
    if (!result.date) {
        const els = document.querySelectorAll('[class*="date" i], [class*="time" i], [class*="Date"], [class*="Time"]');
        for (const el of els) {
            const t = el.innerText.trim();
            if (t && t.length < 60) { result.date = t; break; }
        }
    }

    // 4) 텍스트 패턴으로 날짜 찾기 (모든 leaf 노드 순회)
    if (!result.date) {
        const datePattern = /\\d{4}[.\\-/]\\d{1,2}[.\\-/]\\d{1,2}|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]* \\d{1,2},?\\s*\\d{4}|\\d{4}년 \\d{1,2}월 \\d{1,2}일/i;
        const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
        let node;
        while ((node = walker.nextNode())) {
            const t = node.textContent.trim();
            if (datePattern.test(t) && t.length < 60) {
                result.date = t;
                break;
            }
        }
    }

    // ── 본문 ─────────────────────────────────────
    // 1순위: 사이트 고유 본문 클래스 (진단으로 확인된 실제 클래스명)
    const specificEl = document.querySelector(
        '.er-article-detail__content, .er-article-content, .fr-view'
    );
    if (specificEl) {
        result.content = specificEl.innerText.trim();
        return result;
    }

    // 2순위: 기사 래퍼에서 사이드바를 제거한 뒤 추출
    const articleWrapper = document.querySelector(
        '.er-article-detail__article, .er-article-detail'
    );
    if (articleWrapper) {
        const clone = articleWrapper.cloneNode(true);
        clone.querySelectorAll(
            '.er-article-detail__recent, .er-article-side, ' +
            '.er-article-side__content, .er-recent-articles'
        ).forEach(el => el.remove());
        const t = clone.innerText.trim();
        if (t) { result.content = t; return result; }
    }

    // 3순위: 링크 밀도 기반 — 링크가 많은 요소(사이드바)를 자동 제외
    const candidates = document.querySelectorAll(
        'article, main, [class*="content"], [class*="body"], [class*="editor"], .ql-editor'
    );
    let best = null, bestScore = 0;
    for (const el of candidates) {
        if (el.closest('header, footer, nav, aside')) continue;
        // 알려진 사이드바 클래스 직접 제외
        if (el.className && /(recent|related|sidebar|side__)/i.test(el.className)) continue;
        const text = el.innerText.trim();
        if (text.length < 30) continue;
        // 링크 밀도 계산: 링크 텍스트 비율이 높을수록 사이드바일 가능성 높음
        let linkLen = 0;
        el.querySelectorAll('a').forEach(a => { linkLen += (a.innerText || '').length; });
        const linkDensity = linkLen / text.length;
        const score = text.length * (1 - linkDensity);
        if (score > bestScore) { bestScore = score; best = el; }
    }
    if (best) { result.content = best.innerText.trim(); return result; }

    // 4순위: main 전체 fallback
    const main = document.querySelector('main');
    if (main) result.content = main.innerText.trim();

    return result;
}
"""

_EXTRACT_LIST_JS = """
() => {
    const posts = [];
    const seen = new Set();

    // /posts/news/숫자 패턴의 링크를 모두 찾기
    const links = document.querySelectorAll('a[href*="/posts/news/"]');
    for (const a of links) {
        const href = a.getAttribute('href') || '';
        const match = href.match(/\\/posts\\/news\\/(\\d+)/);
        if (!match) continue;
        const id = match[1];
        if (seen.has(id)) continue;
        seen.add(id);

        const title = a.innerText.trim();
        if (!title) continue;

        // 날짜: 가장 가까운 조상에서 date/time 요소 탐색
        let date = '';
        let ancestor = a.parentElement;
        for (let i = 0; i < 6 && ancestor; i++, ancestor = ancestor.parentElement) {
            const timeEl = ancestor.querySelector('time');
            if (timeEl) {
                date = timeEl.getAttribute('datetime') || timeEl.innerText.trim();
                break;
            }
            const dateEl = ancestor.querySelector('[class*="date" i], [class*="time" i]');
            if (dateEl && dateEl !== a) {
                const t = dateEl.innerText.trim();
                if (t && t.length < 60) { date = t; break; }
            }
        }

        // 썸네일
        let thumbnail = '';
        let anc2 = a.parentElement;
        for (let i = 0; i < 5 && anc2; i++, anc2 = anc2.parentElement) {
            const img = anc2.querySelector('img');
            if (img) { thumbnail = img.src || img.getAttribute('data-src') || ''; break; }
        }

        posts.push({
            id,
            title,
            date,
            thumbnail,
            url: href.startsWith('http') ? href : 'https://playeternalreturn.com' + href
        });
    }
    return posts;
}
"""


# ─────────────────────────────────────────────
# 목록 수집
# ─────────────────────────────────────────────

async def get_patchnote_list(page, max_pages: int = 5) -> list[dict]:
    posts = []
    seen_ids = set()

    print(f"[목록] {LIST_URL}")
    await page.goto(LIST_URL, wait_until="networkidle", timeout=30000)
    await page.wait_for_timeout(2000)

    for page_num in range(1, max_pages + 1):
        print(f"  [{page_num}페이지] 수집 중...")

        # 1) __NEXT_DATA__ 시도
        next_data = await extract_next_data(page)
        items = []
        if next_data:
            items = parse_list_from_next_data(next_data)
            if items:
                print(f"    __NEXT_DATA__ 에서 {len(items)}개 발견")
                for item in items:
                    post_id = str(item.get("id") or item.get("postId") or item.get("no") or "")
                    if not post_id or post_id in seen_ids:
                        continue
                    seen_ids.add(post_id)
                    title = item.get("title") or item.get("subject") or ""
                    date = (
                        item.get("createdAt") or item.get("publishedAt")
                        or item.get("date") or item.get("regDate") or ""
                    )
                    url = item.get("url") or f"{BASE_URL}/posts/news/{post_id}"
                    posts.append({"id": post_id, "title": title, "date": date, "url": url})

        # 2) DOM에서 링크 추출 (NEXT_DATA 없거나 부족할 때)
        dom_posts = await page.evaluate(_EXTRACT_LIST_JS)
        new_count = 0
        for p in dom_posts:
            if p["id"] in seen_ids:
                continue
            seen_ids.add(p["id"])
            posts.append(p)
            new_count += 1

        print(f"    DOM 에서 신규 {new_count}개 (누적 {len(posts)}개)")

        if new_count == 0 and not items:
            break

        # 다음 페이지
        if page_num < max_pages:
            next_btn = await page.query_selector(
                "button[aria-label*='next' i], [class*='next' i] button, "
                "button:has-text('다음'), a:has-text('다음')"
            )
            if next_btn:
                await next_btn.click()
                await page.wait_for_load_state("networkidle")
                await page.wait_for_timeout(1500)
            else:
                # URL 파라미터 방식
                await page.goto(
                    f"{LIST_URL}&page={page_num + 1}",
                    wait_until="networkidle", timeout=30000
                )
                await page.wait_for_timeout(1500)

    return posts


# ─────────────────────────────────────────────
# 개별 패치노트 내용 수집
# ─────────────────────────────────────────────

async def get_patchnote_content(page, post: dict, debug: bool = False) -> dict:
    print(f"  [{post['id']}] {post['title'][:50]}...")

    # API 인터셉터 등록
    handler, captured = make_api_interceptor()
    page.on("response", handler)

    try:
        await page.goto(post["url"], wait_until="networkidle", timeout=30000)

        # h1 또는 h2가 나타날 때까지 최대 5초 대기
        try:
            await page.wait_for_selector("h1, h2", timeout=5000)
        except Exception:
            pass
        await page.wait_for_timeout(1000)

        page.remove_listener("response", handler)

        title, date, content = post["title"], post.get("date", ""), ""

        # ── 1) __NEXT_DATA__ ──────────────────────────
        next_data = await extract_next_data(page)
        if next_data:
            parsed = parse_post_from_next_data(next_data)
            if parsed["title"]:
                title = parsed["title"]
            if parsed["date"]:
                date = parsed["date"]
            if parsed["content"] and len(parsed["content"]) > 50:
                content = parsed["content"]

        # ── 2) API 인터셉트 결과 ──────────────────────
        if not content:
            for cap in captured:
                body = cap["body"]
                c = _find_in_dict(body, ["content", "body", "html", "contents"])
                if c and len(c) > 50:
                    content = c
                if not date:
                    date = _find_in_dict(body, ["createdAt", "publishedAt", "date", "regDate"]) or date
                if not title or title == post["title"]:
                    t = _find_in_dict(body, ["title", "subject"])
                    if t:
                        title = t

        # ── 3) DOM 스크래핑 ───────────────────────────
        dom = await page.evaluate(_EXTRACT_DETAIL_JS)

        if not title or title == post["title"]:
            title = dom["title"] or title
        if not date:
            date = dom["date"]
        if not content and dom["content"]:
            content = dom["content"]

        # ── 4) content 최후 fallback: main 전체 텍스트 ─
        if not content:
            content = await page.evaluate(
                "() => (document.querySelector('main') || document.body).innerText.trim()"
            )

        # 날짜 정규화: ISO 형식이면 그대로, 아니면 파싱 시도
        date = _normalize_date(date)

        # 디버그: 전체 HTML 저장
        if debug:
            html = await page.content()
            debug_path = OUTPUT_DIR / f"debug_{post['id']}.html"
            debug_path.write_text(html, encoding="utf-8")
            print(f"    [DEBUG] HTML 저장: {debug_path}")

        return {
            **post,
            "title": title,
            "date": date,
            "content": content,
            "crawled_at": datetime.now().isoformat(),
        }

    except Exception as e:
        page.remove_listener("response", handler)
        print(f"    오류: {e}")
        return {**post, "content": "", "date": post.get("date", ""), "crawled_at": "", "error": str(e)}


def _normalize_date(raw: str) -> str:
    """날짜 문자열을 YYYY-MM-DD 형식으로 정규화 (가능할 때)"""
    if not raw:
        return ""
    raw = raw.strip()

    # 이미 ISO 형식
    m = re.search(r"(\d{4}-\d{2}-\d{2})", raw)
    if m:
        return m.group(1)

    # 2026.04.16 or 2026/04/16
    m = re.search(r"(\d{4})[./](\d{1,2})[./](\d{1,2})", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    # April 16, 2026 / Apr 16 2026
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    m = re.search(r"([A-Za-z]{3,9})\s+(\d{1,2}),?\s+(\d{4})", raw)
    if m:
        mon = months.get(m.group(1).lower()[:3])
        if mon:
            return f"{m.group(3)}-{mon}-{int(m.group(2)):02d}"

    # 2026년 4월 16일
    m = re.search(r"(\d{4})년\s*(\d{1,2})월\s*(\d{1,2})일", raw)
    if m:
        return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}"

    return raw  # 파싱 실패 시 원본 반환


# ─────────────────────────────────────────────
# 저장
# ─────────────────────────────────────────────

def save_json(data, path: Path):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[저장] JSON: {path}")


def save_csv(data: list[dict], path: Path):
    if not data:
        return
    fields = ["id", "title", "date", "url", "crawled_at", "content"]
    with open(path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(data)
    print(f"[저장] CSV: {path}")


# ─────────────────────────────────────────────
# 메인
# ─────────────────────────────────────────────

async def main(max_list_pages: int = 3, crawl_content: bool = True,
               headless: bool = True, debug: bool = False):
    print("=== 이터널리턴 패치노트 크롤러 시작 ===\n")

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=headless)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            locale="ko-KR",
        )
        page = await context.new_page()

        print("[1단계] 패치노트 목록 수집")
        posts = await get_patchnote_list(page, max_pages=max_list_pages)
        print(f"\n총 {len(posts)}개 게시글 목록 수집 완료\n")
        save_json(posts, OUTPUT_DIR / "patchnote_list.json")

        if crawl_content and posts:
            print("[2단계] 개별 패치노트 내용 수집")
            detailed = []
            for i, post in enumerate(posts, 1):
                print(f"  ({i}/{len(posts)})", end=" ")
                result = await get_patchnote_content(page, post, debug=debug)
                detailed.append(result)
                await asyncio.sleep(0.5)

            save_json(detailed, OUTPUT_DIR / "patchnotes_full.json")
            save_csv(detailed, OUTPUT_DIR / "patchnotes.csv")

            # 개별 텍스트 파일
            txt_dir = OUTPUT_DIR / "texts"
            txt_dir.mkdir(exist_ok=True)
            for post in detailed:
                if post.get("content"):
                    safe = re.sub(r'[\\/*?:"<>|]', "_", post["title"])[:80]
                    (txt_dir / f"{post['id']}_{safe}.txt").write_text(
                        f"{post['title']}\n{post['date']}\n{post['url']}\n\n{post['content']}",
                        encoding="utf-8",
                    )
            print(f"\n개별 텍스트: {txt_dir}/")

        await browser.close()

    print("\n=== 크롤링 완료 ===")
    print(f"결과: {OUTPUT_DIR.resolve()}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="이터널리턴 패치노트 크롤러")
    parser.add_argument("--pages", type=int, default=3, help="목록 페이지 수 (기본: 3)")
    parser.add_argument("--list-only", action="store_true", help="목록만 수집")
    parser.add_argument("--show-browser", action="store_true", help="브라우저 창 표시")
    parser.add_argument("--debug", action="store_true", help="각 페이지 HTML 저장")
    args = parser.parse_args()

    asyncio.run(main(
        max_list_pages=args.pages,
        crawl_content=not args.list_only,
        headless=not args.show_browser,
        debug=args.debug,
    ))
