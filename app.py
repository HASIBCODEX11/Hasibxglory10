"""
HASIB X GLORY - main file (Railway start command: python app.py)
================================================================
Starts the full bot program (main.py + web_bridge.py) and shows a live
HASIB X GLORY page in the same dark + gold design as the website:

  /           live page: bots online, in match, squads playing / resting, logs
  /live.json  the same numbers as JSON
  /panel      the old HASIB CODER bot panel (owner login)
  /api/ping   health check for Railway
"""
import asyncio
import html
import time

import aiohttp.web

import main as m
import web_bridge as wb

SITE = "https://hasibxglory.lovable.app"
SERVERS = ["BD", "IND", "PK", "US", "EU", "RU", "BR", "INDO", "SG", "VN", "TH", "ME", "NA", "SAC", "TW"]


def _live():
    accs = list(getattr(m.bot_state, "accounts", {}).values())
    status = [str(a.get("status", "")).upper() for a in accs]
    online = sum(1 for s in status if s in ("ONLINE", "IN_MATCH", "SEARCHING"))
    in_match = sum(1 for s in status if "IN_MATCH" in s)
    searching = sum(1 for s in status if s == "SEARCHING")
    launches = list(wb.STATE.get("launches", {}).values())
    now = time.time()
    squads = []
    for r in launches:
        ph = r.get("phase") or "play"
        left = (wb.PLAY_SECONDS if ph == "play" else wb.REST_SECONDS) - (now - float(r.get("phase_at") or now))
        squads.append({"guild": r.get("guild"), "bots": len(r.get("uids") or []), "phase": ph,
                       "minutes_left": max(0, int(left // 60))})
    return {
        "app": "HASIB X GLORY", "version": "V10",
        "website": SITE, "connected": bool(wb.STATE.get("connected")),
        "bots_online": online, "bots_in_match": in_match, "bots_searching": searching, "bots_total": len(accs),
        "squads_playing": sum(1 for q in squads if q["phase"] == "play"),
        "squads_resting": sum(1 for q in squads if q["phase"] == "rest"),
        "play_minutes": wb.PLAY_SECONDS // 60, "rest_minutes": wb.REST_SECONDS // 60,
        "squads": squads,
        "logs": [{"t": l["t"], "level": l["level"], "message": l["message"]} for l in list(wb.HISTORY)[:60]],
    }


PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>HASIB X GLORY · Live bots</title>
<link rel="preconnect" href="https://fonts.googleapis.com"><link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Outfit:wght@500;700;800&family=Manrope:wght@400;600;700&display=swap" rel="stylesheet">
<style>
:root{--bg:#09090b;--card:#121215;--line:#2a2620;--gold:#e8c27a;--gold2:#b8893f;--text:#f4efe6;--muted:#9a9184;--ok:#4ade80;--warn:#fbbf24;--err:#f87171}
*{box-sizing:border-box}body{margin:0;background:radial-gradient(1200px 600px at 50% -200px,#2a2014 0,transparent 60%),var(--bg);color:var(--text);font-family:Manrope,system-ui,sans-serif}
.wrap{max-width:1000px;margin:0 auto;padding:24px 16px 60px}
h1{font-family:Outfit,sans-serif;font-weight:800;font-size:clamp(28px,6vw,44px);margin:8px 0 4px;letter-spacing:.5px}
h1 span{background:linear-gradient(90deg,var(--gold),var(--gold2));-webkit-background-clip:text;background-clip:text;color:transparent}
.sub{color:var(--muted);margin:0 0 20px}
.pill{display:inline-flex;align-items:center;gap:8px;border:1px solid var(--line);border-radius:999px;padding:6px 12px;font-size:12px;font-weight:700}
.dot{width:8px;height:8px;border-radius:50%}
.grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:12px;margin:18px 0}
.card{background:linear-gradient(180deg,#16151a,var(--card));border:1px solid var(--line);border-radius:18px;padding:16px}
.n{font-family:Outfit,sans-serif;font-size:34px;font-weight:800;color:var(--gold)}.l{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:1px}
h2{font-family:Outfit,sans-serif;font-size:18px;margin:26px 0 10px}
.chips{display:flex;flex-wrap:wrap;gap:8px}.chip{border:1px solid var(--line);border-radius:10px;padding:6px 10px;font-weight:700;font-size:13px;color:var(--gold)}
table{width:100%;border-collapse:collapse;font-size:14px}td,th{padding:10px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-weight:600;font-size:12px}
.logs{background:#0b0b0d;border:1px solid var(--line);border-radius:14px;padding:12px;font-family:ui-monospace,monospace;font-size:12px;max-height:380px;overflow:auto}
.logs div{padding:2px 0}.t{color:var(--muted);margin-right:8px}.ok{color:var(--ok)}.warn{color:var(--warn)}.error{color:var(--err)}
a.btn{display:inline-block;margin-top:14px;background:linear-gradient(90deg,var(--gold),var(--gold2));color:#1a1206;font-weight:800;text-decoration:none;border-radius:12px;padding:12px 18px}
.foot{color:var(--muted);font-size:12px;margin-top:30px}
</style></head><body><div class="wrap">
<span class="pill" id="conn"><span class="dot"></span>…</span>
<h1>HASIB <span>X</span> GLORY</h1>
<p class="sub">Free Fire guild glory bots · <span id="cycle"></span></p>
<div class="grid">
 <div class="card"><div class="n" id="on">0</div><div class="l">Bots online</div></div>
 <div class="card"><div class="n" id="im">0</div><div class="l">In match</div></div>
 <div class="card"><div class="n" id="sp">0</div><div class="l">Squads playing</div></div>
 <div class="card"><div class="n" id="sr">0</div><div class="l">Squads resting</div></div>
</div>
<h2>Squads</h2><div class="card"><table><thead><tr><th>Guild</th><th>Bots</th><th>Now</th><th>Next change</th></tr></thead><tbody id="sq"></tbody></table></div>
<h2>Servers</h2><div class="chips">__SERVERS__</div>
<h2>Price</h2><div class="card"><div class="n">৳50</div><div class="l">1 credit = 1 squad of 4 bots · bKash 01716933342</div>
<a class="btn" href="__SITE__">Open website</a></div>
<h2>Live logs</h2><div class="logs" id="lg"></div>
<p class="foot">Contact Telegram @hasib_hii · Owner panel: <a style="color:var(--gold)" href="/panel">/panel</a></p>
</div><script>
const e=s=>String(s).replace(/[&<>"]/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;"}[c]));
async function tick(){try{const d=await (await fetch('/live.json',{cache:'no-store'})).json();
const c=document.getElementById('conn');c.innerHTML='<span class="dot" style="background:'+(d.connected?'var(--ok)':'var(--err)')+'"></span>'+(d.connected?'Connected to website':'Not connected to website');
on.textContent=d.bots_online;im.textContent=d.bots_in_match;sp.textContent=d.squads_playing;sr.textContent=d.squads_resting;
cycle.textContent='play '+d.play_minutes+' min · rest '+d.rest_minutes+' min, again and again';
sq.innerHTML=d.squads.length?d.squads.map(q=>'<tr><td>'+e(q.guild)+'</td><td>'+q.bots+'</td><td class="'+(q.phase=='play'?'ok':'warn')+'">'+(q.phase=='play'?'Playing':'Resting')+'</td><td>'+q.minutes_left+' min</td></tr>').join(''):'<tr><td colspan=4 style="color:var(--muted)">No squads yet</td></tr>';
lg.innerHTML=d.logs.map(l=>'<div><span class="t">'+new Date(l.t*1000).toLocaleTimeString()+'</span><span class="'+e(l.level)+'">'+e(l.message)+'</span></div>').join('')||'<span class="t">No logs yet</span>';
}catch(err){}}
tick();setInterval(tick,4000);
</script></body></html>"""


async def live_page(request):
    chips = "".join(f'<span class="chip">{html.escape(s)}</span>' for s in SERVERS)
    body = PAGE.replace("__SERVERS__", chips).replace("__SITE__", SITE)
    return aiohttp.web.Response(text=body, content_type="text/html")


async def live_json(request):
    return aiohttp.web.json_response(_live())


def setup(app):
    app.router.add_get("/", live_page)
    app.router.add_get("/live.json", live_json)


m.WEB_EXTRA_SETUP = setup

if __name__ == "__main__":
    try:
        asyncio.run(m.main())
    except KeyboardInterrupt:
        m.print_warning("stopped")
