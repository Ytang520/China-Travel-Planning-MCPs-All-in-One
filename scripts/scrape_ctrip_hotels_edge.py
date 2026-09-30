"""Scrape the top 20 hotels from a Ctrip hotel list page using Microsoft Edge.

Drives the system-installed Edge via Playwright (channel="msedge", no browser
download needed). If the list does not render (login wall / anti-bot), injects
the cookies from ctrip-cookies.json via context.add_cookies() -- this CAN set
the HttpOnly "cticket" login ticket that document.cookie cannot.

Usage:
    .venv/Scripts/python.exe scripts/scrape_ctrip_hotels_edge.py [--headed]
"""
import argparse
import asyncio
import json
import sys
from pathlib import Path

from playwright.async_api import async_playwright

URL = (
    "https://hotels.ctrip.com/hotels/list/?flexType=1&cityId=477&provinceId=20&countryId=1"
    "&cityName=%E6%AD%A6%E6%B1%89&destName=%E6%AD%A6%E6%B1%89"
    "&searchWord=%E6%AD%A6%E6%B1%89%E7%AB%99-%E4%B8%9C%E5%87%BA%E5%8F%A3"
    "&searchType=T&searchValue=10|13306087*10*30.6076444|114.4256694|%E6%AD%A6%E6%B1%89%E7%AB%99-%E4%B8%9C%E5%87%BA%E5%8F%A3|13306087"
    "&checkin=2026-10-01&checkout=2026-10-03&crn=1"
    "&listFilters=29~1*29*1~2*2,4~2*4*2,75~TAG_495*75*495,17~5*17*5,15~Range*15*250~400,80~2*80*2"
    "&curr=CNY&locale=zh-CN&old=1"
)
COOKIE_FILE = Path(__file__).resolve().parent.parent / "ctrip-cookies.json"

EXTRACT_JS = """
async () => {
  const sleep = (ms) => new Promise(r => setTimeout(r, ms));
  const collect = () => {
    const list = document.querySelector('.hotel-list');
    if (!list) return [];
    return [...list.children]
      .filter(el => (el.innerText || '').includes('查看详情'))
      .map(el => {
        const text = el.innerText;
        const lines = text.split('\\n').map(s => s.trim()).filter(Boolean);
        const prices = (text.match(/¥[\\d,]+/g) || []).map(p => parseInt(p.replace(/[¥,]/g, ''), 10));
        const ariaStar = [...el.querySelectorAll('[aria-label]')]
          .map(n => n.getAttribute('aria-label'))
          .find(a => /out of 5/.test(a || '')) || '';
        const distance = (lines.find(l => l.startsWith('距')) || '').replace('查看地图', '').trim();
        const reviews = (lines.find(l => l.includes('条点评')) || '').replace(/^(超棒|很好|不错|一般|差)/, '');
        // Reviews and hotel names can contain 房/床; only trust the room-name node.
        const room = (el.querySelector('.room-info .room-name')?.innerText || '').trim();
        return {
          name: lines[0] || '',
          stars: (ariaStar || '').split(' ')[0] || '',
          score: lines.find(l => /^\\d\\.\\d$/.test(l)) || '',
          reviews: reviews,
          distance: distance,
          room: room,
          price: prices.length ? prices[prices.length - 1] : null,
        };
      });
  };
  let cards = collect();
  let attempts = 0;
  while (cards.length < 20 && attempts < 12) {
    window.scrollTo(0, document.body.scrollHeight);
    await sleep(1800);
    let next = collect();
    if (next.length === cards.length) {
      const btn = [...document.querySelectorAll('button, div')].find(e => {
        const t = (e.textContent || '').trim();
        return e.children.length === 0 && (t === '加载更多' || t === '查看更多' || t.includes('加载更多'));
      });
      if (btn) { btn.click(); await sleep(2500); next = collect(); }
    }
    cards = next;
    attempts++;
  }
  return cards.slice(0, 20);
}
"""


async def dump_state(page, label: str) -> None:
    state = await page.evaluate(
        """() => ({
            title: document.title,
            url: location.href,
            hasList: !!document.querySelector('.hotel-list'),
            bodySnippet: (document.body.innerText || '').slice(0, 400)
        })"""
    )
    print(f"[{label}] title={state['title']!r}", file=sys.stderr)
    print(f"[{label}] url={state['url']}", file=sys.stderr)
    print(f"[{label}] hasList={state['hasList']}", file=sys.stderr)
    print(f"[{label}] body={state['bodySnippet']!r}", file=sys.stderr)


async def open_list(page) -> list[dict]:
    await page.goto(URL, wait_until="domcontentloaded", timeout=60_000)
    try:
        await page.wait_for_selector(".hotel-list", timeout=25_000)
    except Exception:
        pass
    await page.wait_for_timeout(3_000)
    return await page.evaluate(EXTRACT_JS)


async def inject_cookies(context) -> None:
    data = json.loads(COOKIE_FILE.read_text(encoding="utf-8"))
    cookies = [
        {
            "name": c["name"],
            "value": c["value"],
            "domain": c.get("domain", ".ctrip.com"),
            "path": "/",
            "httpOnly": c.get("httpOnly", False),
        }
        for c in data["cookies"]
    ]
    await context.add_cookies(cookies)
    print(f"[inject] {len(cookies)} cookies set via add_cookies (incl. HttpOnly cticket)", file=sys.stderr)


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--headed", action="store_true")
    args = parser.parse_args()

    async with async_playwright() as p:
        browser = await p.chromium.launch(channel="msedge", headless=not args.headed)
        context = await browser.new_context(locale="zh-CN", viewport={"width": 1366, "height": 900})
        page = await context.new_page()

        injected = False
        cards = await open_list(page)
        await dump_state(page, "pass1")
        if not cards:
            print("[warn] list empty or login wall -> injecting cookies", file=sys.stderr)
            await inject_cookies(context)
            injected = True
            cards = await open_list(page)
            await dump_state(page, "pass2")

        result = {
            "browser": "msedge (system Edge via Playwright)",
            "cookieInjected": injected,
            "count": len(cards),
            "cards": cards,
        }
        out_path = Path(__file__).resolve().parent.parent / "edge_hotels.json"
        out_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"done: {len(cards)} cards -> {out_path}")
        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
