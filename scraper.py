# scraper.py — сборщик пула из каталогов
# Python 3.10+, requests, bs4
import json
import time
import re
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup

POOL_PATH = Path("pool.json")
CATALOGS = [
    "https://www.banki.ru/products/credits/",
    "https://zaimix.ru/",
    "https://vsezaimyonline.ru/",
]
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
TIMEOUT = 10
FORM_HINTS = ["телефон", "phone", "получить", "код", "смс", "sms", "номер"]

def fetch(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        if r.status_code == 200:
            return r.text
    except requests.RequestException:
        pass
    return None

def extract_domains(html: str, base_url: str) -> set[str]:
    soup = BeautifulSoup(html, "html.parser")
    domains = set()
    for a in soup.find_all("a", href=True):
        href = a["href"]
        full = urljoin(base_url, href)
        parsed = urlparse(full)
        if parsed.scheme in ("http", "https") and parsed.netloc:
            domains.add(f"{parsed.scheme}://{parsed.netloc}")
    return domains

def find_form(html: str, base_url: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for form in soup.find_all("form"):
        text = form.get_text(separator=" ").lower()
        action = form.get("action", "")
        if any(hint in text for hint in FORM_HINTS) or any(h in action.lower() for h in ["code", "otp", "sms"]):
            method = form.get("method", "POST").upper()
            url = urljoin(base_url, action) if action else base_url
            inputs = form.find_all("input")
            phone_field = "phone"
            for inp in inputs:
                name = inp.get("name", "").lower()
                if any(x in name for x in ["phone", "tel", "number", "mobile"]):
                    phone_field = inp.get("name")
                    break
            return {
                "name": urlparse(base_url).netloc.replace(".", "_"),
                "url": url,
                "method": method,
                "body": json.dumps({phone_field: "{phone}"}),
                "body_type": "json",
                "profile": "fast",
            }
    return None

def parse_domain(url: str) -> dict | None:
    html = fetch(url)
    if not html:
        return None
    form = find_form(html, url)
    if form:
        print(f"[+] found: {form['name']} -> {form['url']}")
        return form
    return None

def main():
    pool = []
    seen = set()
    if POOL_PATH.exists():
        try:
            pool = json.loads(POOL_PATH.read_text(encoding="utf-8"))
            seen = {ep["url"] for ep in pool}
        except Exception:
            pass

    domains = set()
    print("[*] сбор доменов из каталогов...")
    for cat in CATALOGS:
        print(f"    {cat}")
        html = fetch(cat)
        if not html:
            continue
        found = extract_domains(html, cat)
        domains.update(found)
        print(f"    +{len(found)} доменов")
        time.sleep(1)

    print(f"[*] всего доменов: {len(domains)}, проверка форм...")
    for i, d in enumerate(domains):
        print(f"[{i+1}/{len(domains)}] {d}")
        form = parse_domain(d)
        if form and form["url"] not in seen:
            pool.append(form)
            seen.add(form["url"])
        time.sleep(0.5)

    POOL_PATH.write_text(json.dumps(pool, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] итог: {len(pool)} эндпоинтов в {POOL_PATH}")

if __name__ == "__main__":
    main()
