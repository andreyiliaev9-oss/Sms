# validator.py — валидатор эндпоинтов перед добавлением в пул
# Python 3.10+, requests
import json
import random
import time
from pathlib import Path

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
}

TEST_PHONE = "79990000000"
TIMEOUT = 8


def check_endpoint(ep: dict) -> tuple[bool, str]:
    """Возвращает (жив, причина)."""
    url = ep.get("url", "")
    body = ep.get("body", "").replace("{phone}", TEST_PHONE)
    body_type = ep.get("body_type", "json")

    headers = dict(HEADERS)
    if body_type == "json":
        headers["Content-Type"] = "application/json"
        data = body.encode()
    else:
        headers["Content-Type"] = "application/x-www-form-urlencoded"
        data = body.encode()

    try:
        r = requests.post(url, data=data, headers=headers, timeout=TIMEOUT)
        # успех: 200-299, либо 400/422 (сервер принял, но что-то не так с данными — значит, живой)
        if 200 <= r.status_code < 300:
            return True, "ok"
        if r.status_code in (400, 422):
            return True, "accepted"
        if r.status_code == 429:
            return True, "flood"
        if r.status_code in (401, 403):
            return False, "forbidden"
        if r.status_code == 404:
            return False, "not_found"
        return False, f"code_{r.status_code}"
    except requests.RequestException as e:
        return False, type(e).__name__


def validate_pool(pool_path: str = "pool.json",
                  dead_path: str = "dead.json") -> dict:
    """Проверяет все эндпоинты, мёртвые выкидывает в dead.json."""
    path = Path(pool_path)
    if not path.exists():
        return {"total": 0, "alive": 0, "dead": 0, "details": []}

    pool = json.loads(path.read_text(encoding="utf-8"))
    alive, dead, details = [], [], []

    for i, ep in enumerate(pool):
        is_alive, reason = check_endpoint(ep)
        details.append({"name": ep.get("name", "?"), "reason": reason, "alive": is_alive})
        print(f"[{i+1}/{len(pool)}] {ep.get('name')}: {reason}")

        if is_alive:
            alive.append(ep)
        else:
            dead.append(ep)
        time.sleep(random.uniform(0.1, 0.4))

    path.write_text(json.dumps(alive, ensure_ascii=False, indent=2), encoding="utf-8")
    Path(dead_path).write_text(json.dumps(dead, ensure_ascii=False, indent=2), encoding="utf-8")

    return {
        "total": len(pool),
        "alive": len(alive),
        "dead": len(dead),
        "details": details,
    }


if __name__ == "__main__":
    rep = validate_pool()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
