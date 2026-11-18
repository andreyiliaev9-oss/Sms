# harvester.py — автоматический поиск и обновление пула
# Python 3.10+, requests, bs4, playwright
import asyncio
import json
import random
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

POOL_PATH = Path("pool.json")
CACHE_PATH = Path("pool_healthy.json")
SEEDS_PATH = Path("seeds.json")

# Источники: каталоги МФО, доставки, знакомства, банки
DEFAULT_SEEDS = [
    "https://www.banki.ru/products/credits/",
    "https://zaimix.ru/",
    "https://vsezaimyonline.ru/",
    "https://findozor.net/zaimy/po-sms/",
    "https://www.1mbank.ru/zaimy/po-sms/",
]

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}

# Ключи для поиска форм
FORM_HINTS = ["телефон", "phone", "получить код", "смс", "sms", "номер", "отправить"]


def load_seeds() -> list[str]:
    if SEEDS_PATH.exists():
        return json.loads(SEEDS_PATH.read_text(encoding="utf-8"))
    return DEFAULT_SEEDS


def load_pool() -> list[dict]:
    if POOL_PATH.exists():
        return json.loads(POOL_PATH.read_text(encoding="utf-8"))
    return []


def save_pool(pool: list[dict]) -> None:
    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2),
                         encoding="utf-8")


def extract_domains(html: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    domains = set()
    for a in soup.find_all("a", href=True):
        href = urljoin(base_url, a["href"])
        parsed = urlparse(href)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            domains.add(f"{parsed.scheme}://{parsed.netloc}")
    return domains


async def find_api_via_playwright(domain: str) -> dict | None:
    """Ищет форму, перехватывает сетевой запрос при отправке."""
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        captured = []

        page.on("request", lambda req: captured.append(req) if req.method == "POST" else None)

        try:
            await page.goto(domain, timeout=15000, wait_until="domcontentloaded")
            # Ищем форму с телефоном
            forms = await page.query_selector_all("form")
            for form in forms:
                text = (await form.inner_text()).lower()
                if any(h in text for h in FORM_HINTS):
                    # Пытаемся заполнить телефон и отправить
                    inputs = await form.query_selector_all("input")
                    for inp in inputs:
                        name = (await inp.get_attribute("name") or "").lower()
                        if any(x in name for x in ["phone", "tel", "number"]):
                            await inp.fill("79990000000")
                            break
                    btn = await form.query_selector("button[type='submit'], button")
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(3000)
        except Exception:
            pass
        finally:
            await browser.close()

        for req in captured:
            url = req.url
            if any(h in url.lower() for h in ["code", "otp", "sms", "send", "auth"]):
                body = req.post_data or "{}"
                return {
                    "name": urlparse(domain).netloc.replace(".", "_"),
                    "url": url,
                    "method": "POST",
                    "body": body.replace("79990000000", "{phone}") if "79990000000" in body else '{"phone":"{phone}"}',
                    "body_type": "json" if body.strip().startswith("{") else "form",
                    "profile": "fast",
                }
    return None


def crawl_catalogs() -> set[str]:
    """Собирает домены из каталогов."""
    domains = set()
    for seed in load_seeds():
        print(f"[crawl] {seed}")
        try:
            r = requests.get(seed, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                found = extract_domains(r.text, seed)
                domains.update(found)
                print(f"  +{len(found)} domains")
        except Exception as e:
            print(f"  error: {e}")
        time.sleep(1)
    return domains


async def harvest() -> dict:
    """Основной цикл: каталоги -> домены -> API -> пул."""
    pool = load_pool()
    known_urls = {ep["url"] for ep in pool}

    domains = crawl_catalogs()
    print(f"[harvest] total domains: {len(domains)}, checking...")

    new_count = 0
    for i, domain in enumerate(list(domains)[:100]):  # лимит на прогон
        print(f"[{i+1}/{min(len(domains), 100)}] {domain}")
        ep = await find_api_via_playwright(domain)
        if ep and ep["url"] not in known_urls:
            pool.append(ep)
            known_urls.add(ep["url"])
            new_count += 1
            print(f"  [+] {ep['name']} -> {ep['url']}")

    save_pool(pool)
    return {"total": len(pool), "new": new_count, "domains": len(domains)}


def auto_update_loop(interval_hours: int = 6):
    """Фоновое обновление пула."""
    while True:
        time.sleep(interval_hours * 3600)
        print("[auto] harvest starting...")
        try:
            rep = asyncio.run(harvest())
            print(f"[auto] done: {rep}")
        except Exception as e:
            print(f"[auto] error: {e}")


if __name__ == "__main__":
    import sys
    if "--daemon" in sys.argv:
        auto_update_loop()
    else:
        rep = asyncio.run(harvest())
        print(json.dumps(rep, ensure_ascii=False, indent=2))
