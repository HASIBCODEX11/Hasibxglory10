"""
HASIB X GLORY - WEBSITE BRIDGE
==============================
Connects this bot program (main.py) to your HASIB X GLORY website.

  * Every 20 s it asks the website for new squads (users who spent credits).
  * It starts the bots in that guild (website bot accounts, or new ones it creates).
  * Every 3 minutes it sends the squad status / glory back to the website.
  * When the website says "stop" (squad reached its glory goal, owner stopped it,
    refund) the bots of that squad are switched off and removed.
  * Owner squads have no glory limit and keep running.
  * CS / CS Rank / BR / fast mode switches from the website are applied here.
  * Every bot sends the guild join request again every 5 minutes for 1 hour.
  * Guild name, level and EXP are sent to the website (shown on the squad card).
  * V9: "match found / playing / finished" of every bot shows on the website Live logs,
    faster match search, game version auto-fallback (no more "version config failed").
  * V10: every squad plays 1 hour 50 minutes, then rests (offline) 10 minutes, then comes
    back online by itself - every 2 hours (HX_PLAY_MIN / HX_REST_MIN change it).
  * V10: app.py shows a live HASIB X GLORY page (bots online, in match, squads, logs).
  * "Restart" on a squad (website) stops + starts that squad's bots again.
  * "Restart bot program" (owner panel or /restartbots on Telegram) exits this
    program; Railway starts it again (restartPolicyType ALWAYS) and every
    active squad is launched again automatically.

Optional variables on Railway / Render (Variables tab):
  (V9: the website link and key are already built in - no variable needed.
   Set them only if you pressed "Make new key" in the owner panel.)
  HX_WEB_URL     = your website link
  HX_ENGINE_KEY  = website Owner panel -> "Telegram & bot" -> key
Optional:
  HX_GLORY_FIELD = number of the "glory" field in the guild info log line
                   ([GUILD ...] info fields: {...}). Without it the website shows
                   status only, not glory numbers.
"""
import asyncio
import collections
import json
import os
import time

import aiohttp

# Built-in values: the program connects to the website without any Railway variable.
# HX_WEB_URL / HX_ENGINE_KEY on Railway override them (needed only after "Make new key").
DEFAULT_WEB_URL = "https://project--cb25af95-38ec-44b2-9279-f43f47644134-dev.lovable.app"
DEFAULT_ENGINE_KEY = "hKbulgrvH6nHxC6PLfGd3zynvKf51HtRVNF7aptXjseofLa0"
WEB_URL = (os.environ.get("HX_WEB_URL", "").strip() or DEFAULT_WEB_URL).rstrip("/")
ENGINE_KEY = os.environ.get("HX_ENGINE_KEY", "").strip() or DEFAULT_ENGINE_KEY
BOT_NAME_PREFIX = os.environ.get("HX_NAME_PREFIX", "hxglory").strip()[:7] or "hxglory"
POLL_SECONDS = 6
REPORT_SECONDS = 180
STATE_FILE = "web_bridge_state.json"
PLAY_SECONDS = max(60, int(float(os.environ.get("HX_PLAY_MIN", "110") or 110) * 60))   # play 1 hour 50 minutes ...
REST_SECONDS = max(30, int(float(os.environ.get("HX_REST_MIN", "10") or 10) * 60))   # ... then rest 10 minutes
HISTORY = collections.deque(maxlen=200)   # last log lines for the app.py live page
STATE = {"launches": {}, "connected": False, "last_poll": 0}
REGION_MAP = {"INDO": "ID"}  # website server code -> bot program region code


_LOGS = []   # live log lines waiting to be sent to the website


def _log(m, lid, msg, level="info"):
    """Show a line in the console AND on the website Live logs."""
    msg = str(msg)[:300]
    try:
        (m.print_warning if level in ("warn", "error") else m.print_info)(f"[WEB] {msg}")
    except Exception:
        pass
    _LOGS.append({"launch_id": lid, "level": level, "message": msg})
    HISTORY.appendleft({"t": time.time(), "level": level, "message": msg})
    if len(_LOGS) > 1000:
        del _LOGS[:500]


async def _flush_logs(s):
    if not _LOGS:
        return
    batch = _LOGS[:200]
    try:
        async with s.post(WEB_URL + "/api/public/engine/logs", json={"logs": batch}) as r:
            if r.status == 200:
                del _LOGS[:len(batch)]
            elif r.status in (400, 401):
                del _LOGS[:len(batch)]   # bad line / wrong key: do not retry forever
    except Exception:
        pass


async def _log_pump(s):
    while True:
        await _flush_logs(s)
        await asyncio.sleep(3)


def _load_state():
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("launches"), dict):
                return d
    except Exception:
        pass
    return {"launches": {}}


def _save_state(st):
    try:
        tmp = STATE_FILE + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(st, f, indent=2)
        os.replace(tmp, STATE_FILE)
    except Exception:
        pass


def _guild_glory(m, gid):
    info = getattr(m, "_guild_info", {}).get(str(gid)) or {}
    g = info.get("glory")
    return int(g) if isinstance(g, int) else None


def _guild_report(m, rec):
    info = getattr(m, "_guild_info", {}).get(str(rec.get("guild"))) or {}
    uids = set(rec.get("uids") or [])
    exp = 0
    try:
        for a in list(m.bot_state.accounts.values()):
            if str(a.get("auth_uid") or a.get("uid") or "") in uids:
                exp += int(a.get("gained_exp", 0) or 0)
    except Exception:
        pass
    out = {"exp": max(exp, 0)}
    if info.get("name"):
        out["name"] = str(info["name"])[:60]
    if isinstance(info.get("level"), int):
        out["level"] = info["level"]
    return out


JOIN_RESEND_SECONDS = 300   # re-send the guild join request every 5 minutes ...
JOIN_RESEND_ROUNDS = 12     # ... for the first hour (leader may accept late / guild was full)


async def _resend_join(m, rec):
    uids = set(rec.get("uids") or [])
    sent = 0
    for ad in list(m.bot_state.account_credentials.values()):
        if str(ad.get("auth_uid") or "") in uids and ad.get("token"):
            try:
                if await m.join_clan(ad["token"], rec["guild"]):
                    sent += 1
            except Exception:
                pass
            await asyncio.sleep(0.5)
    if sent:
        _log(m, rec.get("lid"), f"📨 join request sent again to guild {rec['guild']} by {sent} bots")


_EVENT_LAST = {}


def _install_event_hook(m, st):
    """Match found / playing / finished from main.py -> website Live logs (with the bot name)."""
    def hook(game_uid, msg, level):
        lid = None
        nick = None
        try:
            acc = m.bot_state.accounts.get(str(game_uid)) or {}
            nick = acc.get("nickname") or acc.get("name")
            auth = str(acc.get("auth_uid") or "")
            if not auth:
                for a_uid, g_uid in list(m.bot_state.auth_to_game_id.items()):
                    if str(g_uid) == str(game_uid):
                        auth = str(a_uid)
                        break
            for rec in st["launches"].values():
                if auth and auth in (rec.get("uids") or []):
                    lid = rec["lid"]
                    break
        except Exception:
            pass
        if not lid:
            return
        key = (str(game_uid), msg)
        now = time.time()
        if now - _EVENT_LAST.get(key, 0) < 20:
            return
        _EVENT_LAST[key] = now
        if len(_EVENT_LAST) > 5000:
            _EVENT_LAST.clear()
        _log(m, lid, f"{nick or game_uid}: {msg}", level)
    m.WEB_EVENT_HOOK = hook


def _apply_settings(m, s):
    rt = getattr(m, "_runtime", None)
    if not isinstance(rt, dict):
        return
    changed = False
    for web_key, rt_key in (("cs_mode", "cs_mode"), ("br_mode", "br_mode"), ("cs_rank_mode", "cs_rank"), ("fast_mode", "fast_mode")):
        if web_key in s and s[web_key] is not None and rt.get(rt_key) != bool(s[web_key]):
            rt[rt_key] = bool(s[web_key])
            changed = True
    if changed:
        try:
            m.save_config()
        except Exception:
            pass
        m.print_info(f"[WEB] modes -> CS {rt.get('cs_mode')} | CS RANK {rt.get('cs_rank')} | BR {rt.get('br_mode')} | FAST {rt.get('fast_mode')}")


async def _post_report(m, s, body):
    try:
        async with s.post(WEB_URL + "/api/public/engine/report", json=body) as r:
            if r.status != 200:
                m.print_warning(f"[WEB] report HTTP {r.status}: {(await r.text())[:200]}")
                return None
            return await r.json()
    except Exception as e:
        m.print_warning(f"[WEB] report: {e}")
        return None


def _stop_launch(m, st, lid):
    rec = st["launches"].pop(lid, None)
    if not rec:
        return
    uids = set(rec.get("uids") or [])
    for u in uids:
        try:
            m.RESTING.discard(str(u))
        except Exception:
            pass
    # remove from accounts.json first, otherwise the auto-restart supervisor starts them again
    try:
        keep = [a for a in m._read_accounts_file() if str(a.get("uid")) not in uids]
        m._write_accounts_file(keep)
    except Exception as e:
        m.print_warning(f"[WEB] stop {lid}: {e}")
    for uid in uids:
        t = m.bot_state.account_workers.pop(uid, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass
    _log(m, lid, f"⏹ squad stopped — {len(uids)} bots off")


def _rest_launch(m, rec):
    """Hourly rest: the squad's bots go offline for REST_SECONDS."""
    uids = [str(u) for u in rec.get("uids") or []]
    for uid in uids:
        m.RESTING.add(uid)
        t = m.bot_state.account_workers.pop(uid, None)
        if t:
            try:
                t.cancel()
            except Exception:
                pass
    rec["phase"] = "rest"
    rec["phase_at"] = time.time()
    _log(m, rec.get("lid"), f"😴 squad resting {REST_SECONDS // 60} min ({len(uids)} bots offline) — back online by itself")


def _wake_launch(m, rec):
    uids = {str(u) for u in rec.get("uids") or []}
    for uid in uids:
        m.RESTING.discard(uid)
    n = 0
    try:
        for a in m._read_accounts_file():
            if str(a.get("uid")) in uids:
                t = m.bot_state.account_workers.get(str(a.get("uid")))
                if t is None or t.done():
                    m._launch_record(dict(a))
                    n += 1
    except Exception as e:
        m.print_warning(f"[WEB] wake: {e}")
    rec["phase"] = "play"
    rec["phase_at"] = time.time()
    _log(m, rec.get("lid"), f"🔁 squad back online ({n} bots) — playing {PLAY_SECONDS // 60} min", "ok")


async def _start_launch(m, s, st, job):
    lid = job["id"]
    if lid in st["launches"]:
        # restart: switch the old bots off first
        _stop_launch(m, st, lid)
        await asyncio.sleep(2)
    try:
        for b in job.get("bots") or []:
            m.RESTING.discard(str(b.get("uid")))
    except Exception:
        pass
    gid = str(job["guild_id"])
    region = REGION_MAP.get(job.get("region"), job.get("region") or "BD")
    bots_out = []
    try:
        site_bots = job.get("bots") or []
        if site_bots:
            _log(m, lid, f"♻ starting {len(site_bots)} saved bots for guild {gid} ({region})")
            existing = m._read_accounts_file()
            uids = {str(b["uid"]) for b in site_bots}
            existing = [a for a in existing if str(a.get("uid")) not in uids]
            recs = []
            for b in site_bots:
                rec = {"uid": str(b["uid"]), "password": str(b["password"]), "region": region,
                       "clan_id": gid, "web_launch": lid}
                existing.append(rec)
                recs.append(rec)
                bots_out.append(b)
            m._write_accounts_file(existing)
            for rec in recs:
                old = m.bot_state.account_workers.get(rec["uid"])
                if old:
                    try:
                        old.cancel()
                    except Exception:
                        pass
                m._launch_record(dict(rec))
                await asyncio.sleep(0.2)
            _log(m, lid, f"🚀 {len(recs)} bots online → they send the join request to guild {gid}", "ok")
        else:
            # create fresh bots, 4 per squad, named hxglory12345
            squads = max(1, int(job.get("squads") or 1))
            per = max(1, int(job.get("bot_count") or 4 * squads) // squads)
            _log(m, lid, f"⚡ creating {per * squads} new bots ({BOT_NAME_PREFIX}…) for guild {gid} · {region}")

            def _progress(msg):
                t = str(msg)
                low = t.lower()
                if "failed" in low or "error" in low or "fail" in low:
                    _log(m, lid, f"⚠ {t}", "warn")

            for _ in range(squads):
                while m.bot_state.creating:
                    await asyncio.sleep(2)
                created = await m.create_four_accounts(region, gid, per, "", BOT_NAME_PREFIX, "", on_progress=_progress) or []
                for a in created:
                    b = {"uid": str(a.get("auth_uid")), "password": str(a.get("auth_password")),
                         "token": a.get("token"), "game_uid": str(a.get("account_id") or a.get("uid") or ""),
                         "nickname": a.get("nickname") or a.get("name"), "region": region}
                    bots_out.append(b)
                    _log(m, lid, f"✅ acc created {b['nickname']} | game UID {b['game_uid']} | {region}", "ok")
                    # send the guild join request right away (the worker sends it again after login)
                    try:
                        if a.get("token") and await m.join_clan(a["token"], gid):
                            _log(m, lid, f"📨 {b['nickname']} sent join request to guild {gid}", "ok")
                        else:
                            why = str(getattr(m, "_LAST_CLAN_ERR", {}).get(gid, ""))
                            if "waiting" in why:
                                _log(m, lid, f"📨 {b['nickname']}: join request waiting — accept it in Guild → Requests", "ok")
                            else:
                                _log(m, lid, f"⚠ {b['nickname']}: join request refused ({why or 'guild full / wrong ID?'})", "warn")
                    except Exception as e:
                        _log(m, lid, f"⚠ {b['nickname']} join error: {str(e)[:120]}", "warn")
                    await asyncio.sleep(0.3)
            # tag them so they can be stopped later
            uids = {b["uid"] for b in bots_out}
            accs = m._read_accounts_file()
            for a in accs:
                if str(a.get("uid")) in uids:
                    a["web_launch"] = lid
            m._write_accounts_file(accs)

        if not bots_out:
            _log(m, lid, "❌ no bot could be created / logged in — credit refunded", "error")
            await _post_report(m, s, {"launch_id": lid, "status": "failed", "error": "Bots could not be created. Credit refunded."})
            return
        st["launches"][lid] = {"lid": lid, "guild": gid, "uids": [str(b["uid"]) for b in bots_out],
                               "baseline": _guild_glory(m, gid), "last_report": time.time() - REPORT_SECONDS + 60, "last_join": time.time(),
                               "unlimited": bool(job.get("is_unlimited")), "phase": "play", "phase_at": time.time()}
        _save_state(st)
        await _post_report(m, s, {"launch_id": lid, "status": "running", "bots": bots_out})
        _log(m, lid, f"🏆 squad running in guild {gid} with {len(bots_out)} bots — accept them in Guild → Requests", "ok")
    except Exception as e:
        _log(m, lid, f"❌ launch error: {str(e)[:200]}", "error")
        await _post_report(m, s, {"launch_id": lid, "status": "failed", "error": f"Launch error: {str(e)[:200]}"})


async def run(m):
    if not WEB_URL or not ENGINE_KEY:
        m.print_info("[WEB] website bridge is off (set HX_WEB_URL and HX_ENGINE_KEY to turn it on)")
        return
    m.print_info(f"[WEB] website bridge on -> {WEB_URL}")
    _log(m, None, "🟢 bot program connected to the website")
    st = _load_state()
    STATE["launches"] = st["launches"]
    for rec in st["launches"].values():      # program restarted: every squad starts a fresh play hour
        rec["phase"] = "play"
        rec["phase_at"] = time.time()
    _install_event_hook(m, st)
    booted = False
    restart_seen = None
    async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=25), headers={"x-engine-key": ENGINE_KEY}) as s:
        asyncio.create_task(_log_pump(s))
        while True:
            try:
                data = None
                url = WEB_URL + "/api/public/engine/jobs" + ("" if booted else "?boot=1")
                async with s.get(url) as r:
                    if r.status == 200:
                        data = await r.json()
                        booted = True
                        STATE["connected"] = True
                        STATE["last_poll"] = time.time()
                    else:
                        m.print_warning(f"[WEB] jobs HTTP {r.status} from {WEB_URL} (check HX_WEB_URL / HX_ENGINE_KEY)")
                if data:
                    ra = data.get("restart_at")
                    if restart_seen is None:
                        restart_seen = ra or ""
                    elif ra and ra != restart_seen:
                        _log(m, None, "🔄 owner pressed RESTART — bot program restarting now")
                        _save_state(st)
                        await _flush_logs(s)
                        await asyncio.sleep(1)
                        os._exit(1)
                    _apply_settings(m, data.get("settings") or {})
                    for lid in data.get("stop") or []:
                        if lid in st["launches"]:
                            _stop_launch(m, st, lid)
                    for job in data.get("jobs") or []:
                        asyncio.create_task(_start_launch(m, s, st, job))

                now = time.time()
                for lid, rec in list(st["launches"].items()):
                    ph = rec.get("phase") or "play"
                    since = now - float(rec.get("phase_at") or now)
                    if ph == "play" and since >= PLAY_SECONDS:
                        _rest_launch(m, rec)
                    elif ph == "rest" and since >= REST_SECONDS:
                        _wake_launch(m, rec)
                    if rec.get("join_rounds", 0) < JOIN_RESEND_ROUNDS and now - rec.get("last_join", 0) >= JOIN_RESEND_SECONDS:
                        rec["join_rounds"] = rec.get("join_rounds", 0) + 1
                        rec["last_join"] = now
                        asyncio.create_task(_resend_join(m, rec))
                    if now - rec.get("last_report", 0) < REPORT_SECONDS:
                        continue
                    rec["last_report"] = now
                    body = {"launch_id": lid, "status": "running", "guild": _guild_report(m, rec)}
                    cur = _guild_glory(m, rec["guild"])
                    if cur is not None:
                        if rec.get("baseline") is None:
                            rec["baseline"] = cur
                        body["glory_gained"] = max(0, cur - int(rec["baseline"]))
                    res = await _post_report(m, s, body)
                    if res and res.get("action") == "stop":
                        _stop_launch(m, st, lid)
                _save_state(st)
            except Exception as e:
                m.print_warning(f"[WEB] bridge: {e}")
            await asyncio.sleep(POLL_SECONDS)
