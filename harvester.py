import asyncio
import json
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

POOL_PATH = Path("pool.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
FORM_HINTS = ["телефон", "phone", "получить код", "смс", "sms", "номер", "отправить"]

SEEDS = [
    "https://zaimix.ru/",
    "https://vsezaimyonline.ru/",
    "https://findozor.net/zaimy/po-sms/",
]

def load_pool():
    try:
        with open("pool.json", "r") as f:
            return json.load(f)
    except:
        return []

def save_pool(pool):
    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")

def extract_domains(html, base):
    soup = BeautifulSoup(html, "html.parser")
    return {urljoin(base, a["href"]) for a in soup.find_all("a", href=True) if urljoin(base, a["href"]).startswith("http")}

async def find_api(domain):
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        captured = []
        page.on("request", lambda req: captured.append(req) if req.method == "POST" else None)
        try:
            await page.goto(domain, timeout=15000, wait_until="domcontentloaded")
            forms = await page.query_selector_all("form")
            for form in forms:
                text = (await form.inner_text()).lower()
                if any(h in text for h in FORM_HINTS):
                    for inp in await form.query_selector_all("input"):
                        name = (await inp.get_attribute("name") or "").lower()
                        if any(x in name for x in ["phone", "tel", "number"]):
                            await inp.fill("79990000000")
                            break
                    btn = await form.query_selector("button[type='submit'], button")
                    if btn:
                        await btn.click()
                        await page.wait_for_timeout(3000)
        except:
            pass
        finally:
            await browser.close()

        for req in captured:
            if any(h in req.url.lower() for h in ["code", "otp", "sms", "send", "auth"]):
                body = req.post_data or "{}"
                return {
                    "name": urlparse(domain).netloc.replace(".", "_"),
                    "url": req.url, "method": "POST",
                    "body": body.replace("79990000000", "{phone}"),
                    "body_type": "json" if body.startswith("{") else "form",
                    "profile": "fast"
                }
    return None

def validate_pool():
    pool = load_pool()
    if not pool:
        return {"total": 0, "alive": 0, "dead": 0}
    
    alive = []
    for ep in pool:
        url = ep.get("url", "")
        body = ep.get("body", "").replace("{phone}", "79990000000")
        hdrs = {**HEADERS, "Content-Type": "application/json" if ep.get("body_type") == "json" else "application/x-www-form-urlencoded"}
        try:
            r = requests.post(url, data=body.encode(), headers=hdrs, timeout=6)
            if r.status_code in (200, 201, 400, 422, 429):
                alive.append(ep)
        except:
            pass
    save_pool(alive)
    return {"total": len(pool), "alive": len(alive), "dead": len(pool) - len(alive)}

async def harvest():
    pool = load_pool()
    known = {ep["url"] for ep in pool}
    domains = set()
    
    for seed in SEEDS:
        try:
            r = requests.get(seed, headers=HEADERS, timeout=10)
            if r.status_code == 200:
                domains.update(extract_domains(r.text, seed))
        except:
            pass
        time.sleep(1)
        
    for d in list(domains)[:50]:
        ep = await find_api(d)
        if ep and ep["url"] not in known:
            pool.append(ep)
            known.add(ep["url"])
            
    save_pool(pool)
    rep = validate_pool()
    return {"found": len(pool), "alive": rep["alive"], "dead": rep["dead"]}
