# api.py — веб-панель: метрики + управление
# Python 3.10+, fastapi, uvicorn
import asyncio
import json
import logging
import os
from pathlib import Path
import aiohttp

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, StreamingResponse, Response
from pydantic import BaseModel

import cache
import cleanup
from metrics import METRICS
from prom2 import render as prom2_render
from core2 import Registry, Engine, Limiter
from health import healthcheck, load_pool
from scheduler import Target, RoundRobin, RotationRunner, ProfileLimiter

app = FastAPI(title="panel")
log = logging.getLogger("api")
logging.basicConfig(level=logging.INFO)

ADMIN_ID = 8141670312
PROXY_PATH = Path("proxies.txt")
STATE = {"engine": None, "runner": None, "phone": None}
REGISTRY = Registry()
LIMITER = Limiter(start_rps=30.0, min_rps=2.0, max_rps=100.0)
PROFILE_LIMITER = ProfileLimiter(fast_rps=20.0, slow_rps=1.0)
PURGE_INTERVAL = 3600.0
HEALTH_PHONE = "79990000000"


class SingleIn(BaseModel):
    phone: str
    rounds: int = 10


class MultiIn(BaseModel):
    targets: list[dict]


def load_proxies() -> list[str]:
    if not PROXY_PATH.exists():
        return []
    return [ln.strip() for ln in PROXY_PATH.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _seed_registry(alive_eps):
    for ep in alive_eps:
        REGISTRY.add(ep)


async def _notify_bot(text: str) -> None:
    token = os.environ.get("TG_BOT_TOKEN", "")
    if not token:
        return
    try:
        async with aiohttp.ClientSession() as s:
            await s.post(f"https://api.telegram.org/bot{token}/sendMessage",
                         json={"chat_id": ADMIN_ID, "text": text[:3900]})
    except Exception:
        pass


async def maintenance_loop():
    await asyncio.sleep(60)
    while True:
        try:
            await asyncio.sleep(PURGE_INTERVAL)
            log.info("maintenance: start")
            rep = await asyncio.to_thread(cleanup.purge, False)
            log.info("maintenance: purged %d", len(rep["removed"]))
            pool = load_pool()
            if pool:
                hc = await asyncio.to_thread(healthcheck, pool, HEALTH_PHONE)
                alive = hc["_alive_eps"]
                flood = hc["_flood_eps"]
                dead_names = [ep.name for ep in pool
                              if ep not in alive and ep not in flood]
                cache.save(alive, flood, dead_names)
                for ep in alive:
                    REGISTRY.add(ep)
                log.info("maintenance: alive=%d flood=%d dead=%d",
                         len(alive), len(flood), len(dead_names))
        except asyncio.CancelledError:
            return
        except Exception as e:
            log.warning("maintenance failed: %s", e)


@app.on_event("startup")
async def _startup():
    asyncio.create_task(maintenance_loop())


@app.get("/", response_class=HTMLResponse)
async def index():
    return HTMLResponse(INDEX_HTML)


@app.get("/metrics")
async def metrics():
    return METRICS.snapshot()


@app.get("/prom")
async def prom():
    return Response(prom2_render(REGISTRY), media_type="text/plain; version=0.0.4")


@app.get("/stream")
async def stream():
    async def gen():
        while True:
            snap = METRICS.snapshot()
            yield f"data: {json.dumps(snap)}\n\n"
            await asyncio.sleep(1.0)
    return StreamingResponse(gen(), media_type="text/event-stream")


@app.post("/start")
async def start_single(body: SingleIn):
    if STATE["engine"]:
        raise HTTPException(409, "already running")
    pool = load_pool()
    rep = await asyncio.to_thread(healthcheck, pool, body.phone)
    _seed_registry(rep["_alive_eps"])
    eng = Engine(REGISTRY, load_proxies(), workers=16, limiter=LIMITER)
    STATE["engine"] = eng
    STATE["phone"] = body.phone
    async def run():
        try:
            await asyncio.to_thread(eng.run, body.phone, body.rounds)
        finally:
            STATE["engine"] = None
    asyncio.create_task(run())
    return {"status": "started", "phone": body.phone,
            "live": len(rep["_alive_eps"]), "total": rep["total"]}


@app.post("/multi")
async def start_multi(body: MultiIn):
    if STATE["runner"]:
        raise HTTPException(409, "already running")
    targets = [Target(t["phone"], int(t.get("rounds", 10))) for t in body.targets]
    runner = RotationRunner(RoundRobin(targets), load_pool(), load_proxies(), PROFILE_LIMITER)
    STATE["runner"] = runner
    async def run():
        try:
            await asyncio.to_thread(runner.run)
        finally:
            STATE["runner"] = None
    asyncio.create_task(run())
    return {"status": "started", "targets": len(targets)}


@app.post("/stop")
async def stop():
    if STATE["engine"]:
        STATE["engine"].stop()
    if STATE["runner"]:
        STATE["runner"].stop()
    return {"status": "stopping"}


@app.get("/registry")
async def registry():
    snap = REGISTRY.snapshot()
    eps = REGISTRY.all()
    import time
    now = time.monotonic()
    details = []
    for ep in eps:
        details.append({
            "name": ep.name,
            "profile": ep.profile,
            "strikes": ep.strikes,
            "banned": now < ep.banned_until,
            "ban_left": max(0.0, ep.banned_until - now),
        })
    return {"summary": snap, "endpoints": details}


@app.post("/alert")
async def alert_hook(request: Request):
    body = await request.json()
    for a in body.get("alerts", []):
        labels = a.get("labels", {})
        status = a.get("status", "firing")
        name = labels.get("alertname", "?")
        sev = labels.get("severity", "?")
        desc = a.get("annotations", {}).get("description", "")
        log.warning("alert %s [%s/%s] %s", name, sev, status, desc)

        if status != "firing":
            continue

        if name == "FloodRate" and STATE["engine"]:
            STATE["engine"].stop()
            log.warning("flood: engine stopped")
            
        if name == "DiskBackups" and STATE["engine"]:
            STATE["engine"].stop()
            log.warning("disk low: engine stopped")

        if name == "EndpointLongBan":
            ep_name = labels.get("name")
            if ep_name:
                cleanup.mark(ep_name)
                log.warning("dropped: %s", ep_name)

        if name == "RegistryLow":
            log.warning("registry low: regen")
            REGISTRY.regen()

        if name == "ContainerOOM":
            container = labels.get("name", "")
            if container == "panel_api" and STATE["engine"]:
                STATE["engine"].stop()

        await _notify_bot(f"⚠️ {name} [{sev}] {desc}")
    return {"status": "ok"}


@app.post("/purge")
async def purge_endpoint(dry: bool = False):
    rep = await asyncio.to_thread(cleanup.purge, dry)
    return rep


@app.get("/dropped")
async def dropped_list():
    return {"names": sorted(cleanup.load_dropped())}


@app.post("/drop/{name}")
async def drop_one(name: str):
    cleanup.mark(name)
    return {"dropped": name}


@app.post("/undrop/{name}")
async def undrop_one(name: str):
    cleanup.unmark(name)
    return {"undropped": name}

@app.post("/maintenance")
async def force_maintenance():
    rep = await asyncio.to_thread(cleanup.purge, False)
    pool = load_pool()
    hc = await asyncio.to_thread(healthcheck, pool, HEALTH_PHONE) if pool else None
    if hc:
        cache.save(hc["_alive_eps"], hc["_flood_eps"],
                   [ep.name for ep in pool if ep not in hc["_alive_eps"]
                    and ep not in hc["_flood_eps"]])
    return {"purged": len(rep["removed"]), "alive": len(hc["_alive_eps"]) if hc else 0}

INDEX_HTML = """<!doctype html>
<html><head><meta charset="utf-8"><title>panel</title>
<style>
body{font-family:ui-monospace,monospace;background:#0a0a0a;color:#ddd;margin:2rem}
h1{font-size:1rem;color:#888}
.grid{display:grid;grid-template-columns:repeat(4,1fr);gap:1rem;margin:1rem 0}
.card{background:#111;border:1px solid #222;padding:1rem;border-radius:6px}
.card .n{font-size:1.8rem;color:#5f5}
.card .l{font-size:.7rem;color:#666;text-transform:uppercase}
#chart{width:100%;height:220px;background:#0d0d0d;border:1px solid #222;margin-top:1rem}
form{margin:1rem 0}
input,button{background:#111;color:#ddd;border:1px solid #333;padding:.5rem;font-family:inherit}
button{cursor:pointer}
button:hover{border-color:#5f5}
</style></head><body>
<h1>panel · live</h1>
<div class="grid" id="stats"></div>
<canvas id="chart" width="800" height="220"></canvas>
<form id="single">
  <input name="phone" placeholder="phone" required>
  <input name="rounds" type="number" value="10" style="width:5rem">
  <button>start single</button>
  <button type="button" id="stop">stop</button>
</form>
<script>
const hist = [];
const canvas = document.getElementById('chart');
const ctx = canvas.getContext('2d');
function draw() {
  ctx.clearRect(0,0,canvas.width,canvas.height);
  if (hist.length < 2) return;
  const max = Math.max(1, ...hist.map(h => h.fast + h.slow));
  ctx.strokeStyle = '#5f5'; ctx.lineWidth = 2; ctx.beginPath();
  hist.forEach((h,i) => {
    const x = (i/(hist.length-1))*canvas.width;
    const y = canvas.height - (h.fast/max)*canvas.height*0.9;
    if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
  ctx.strokeStyle = '#fa5'; ctx.beginPath();
  hist.forEach((h,i) => {
    const x = (i/(hist.length-1))*canvas.width;
    const y = canvas.height - ((h.fast+h.slow)/max)*canvas.height*0.9;
    if (i===0) ctx.moveTo(x,y); else ctx.lineTo(x,y);
  });
  ctx.stroke();
}
const es = new EventSource('/stream');
es.onmessage = e => {
  const d = JSON.parse(e.data);
  const rp = d.rps_by_profile || {};
  hist.push({fast: rp.fast||0, slow: rp.slow||0});
  if (hist.length > 60) hist.shift();
  draw();
  document.getElementById('stats').innerHTML =
    card('sent', d.totals.sent) + card('failed', d.totals.failed) +
    card('flood', d.totals.flood) + card('rps fast', (rp.fast||0).toFixed(2));
};
function card(l,n){return `<div class="card"><div class="n">${n}</div><div class="l">${l}</div></div>`}
document.getElementById('single').onsubmit = async e => {
  e.preventDefault();
  const f = e.target;
  await fetch('/start', {method:'POST', headers:{'Content-Type':'application/json'},
    body: JSON.stringify({phone:f.phone.value, rounds:+f.rounds.value})});
};
document.getElementById('stop').onclick = async () => { await fetch('/stop', {method:'POST'}); };
</script></body></html>"""
