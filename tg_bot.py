# -*- coding: utf-8 -*-
"""
HASIB X GLORY - Telegram front-end (credit: HASIB CODER)

Same engine as the web panel: send a guild ID, pick a region and 4 / 8 bots and the bots join that guild.
Bots started here show up in the web panel automatically (guild cards + live logs).

  * Owner  : Telegram username @hasib_hii (or ids in TG_OWNER_IDS) -> unlimited bots, settings, /broadcast, ban
  * Users  : max N different guilds per Telegram account (owner sets N, default 5), same per-guild limit as the web
  * Users never see bot names, UIDs or passwords. They only see guild id, name, level, region, bots and EXP.

Style: bold serif button labels, green / red / blue coloured buttons (Bot API `style`), emoji, card layout.
Turn it on from the web panel (Settings > Telegram) or put the token in tg_token.txt / TG_BOT_TOKEN.
"""
import asyncio
import html
import json
import os
import time
import traceback

import httpx

OWNER_USERNAMES = {"hasib_hii"}
OWNER_HANDLE = "@hasib_hii"
OWNER_IDS = {int(x) for x in os.environ.get("TG_OWNER_IDS", "").replace(" ", "").split(",") if x.isdigit()}
USERS_FILE = "tg_users.json"
LINE = "━━━━━━━━━━━━━━━━━━━━"

# Optional Telegram Premium custom emoji for button icons: {"add": "5368...", "stats": "..."}.
# Works for bots whose owner has Premium. Leave empty to use normal emoji only.
ICONS = {}

FLAGS = {"BD": "🇧🇩", "IND": "🇮🇳", "PK": "🇵🇰", "TW": "🇹🇼", "ID": "🇮🇩", "ME": "🇸🇦", "SG": "🇸🇬", "TH": "🇹🇭",
         "VN": "🇻🇳", "BR": "🇧🇷", "NA": "🇺🇸", "US": "🇺🇸", "RU": "🇷🇺", "SAC": "🌎"}


# ---------------------------------------------------------------------- fonts (same idea as the Candy bot)
def _shift(text, up, lo, dg=None):
    out = []
    for ch in str(text):
        o = ord(ch)
        if 65 <= o <= 90:
            out.append(chr(up + o - 65))
        elif 97 <= o <= 122:
            out.append(chr(lo + o - 97))
        elif dg and 48 <= o <= 57:
            out.append(chr(dg + o - 48))
        else:
            out.append(ch)
    return "".join(out)


def serif(t):   # 𝐀𝐝𝐝 𝐛𝐨𝐭𝐬  (button labels)
    return _shift(t, 0x1D400, 0x1D41A)


def sans(t):    # 𝗔𝗗𝗗 𝗕𝗢𝗧𝗦  (card titles)
    return _shift(t, 0x1D5D4, 0x1D5EE, 0x1D7EC)


def esc(x) -> str:
    return html.escape(str(x), quote=False)


def card(title, *lines):
    body = "\n".join(lines)
    return f"✨ <b>{sans(title)}</b> ✨\n{LINE}\n{body}\n{LINE}\n💠 Owner : {OWNER_HANDLE} ⭐"


# ---------------------------------------------------------------------- buttons (coloured like the Candy bot)
def btn(text, data=None, style=None, url=None, icon=None):
    b = {"text": serif(text)}
    if data is not None:
        b["callback_data"] = data
    if url:
        b["url"] = url
    if style in ("primary", "success", "danger"):
        b["style"] = style                      # green = success, red = danger, blue = primary
    if icon:
        b["icon_custom_emoji_id"] = str(icon)
    return b


def kb(rows):
    return {"inline_keyboard": rows}


def plain(markup):
    """Same keyboard without colours / custom icons (fallback if Telegram rejects them)."""
    return {"inline_keyboard": [[{k: v for k, v in b.items() if k not in ("style", "icon_custom_emoji_id")} for b in row]
                                for row in markup.get("inline_keyboard", [])]}


class TgBot:
    def __init__(self, token, adapter, post=None, users_file=USERS_FILE):
        self.token = token
        self.ad = adapter
        self.users_file = users_file
        self.sessions = {}
        self.users = self._load()      # tg id -> {"username","name","guilds":[...],"banned":bool,"blocked":bool}
        self._post = post or self._http_post
        self._client = None
        self.fancy = True              # coloured buttons on; switched off automatically if Telegram refuses them

    # ------------------------------------------------------------------ storage
    def _load(self):
        try:
            with open(self.users_file, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
        except Exception:
            return {}

    def _save(self):
        try:
            tmp = self.users_file + ".tmp"
            with open(tmp, "w", encoding="utf-8") as f:
                json.dump(self.users, f, indent=2, ensure_ascii=False)
            os.replace(tmp, self.users_file)
        except Exception as e:
            print(f"[TG] save users: {e}")

    def _touch(self, user):
        key = str(user["id"])
        new = key not in self.users
        rec = self.users.setdefault(key, {"username": "", "name": "", "guilds": [], "banned": False, "blocked": False,
                                          "first": int(time.time())})
        name = " ".join(x for x in (user.get("first_name"), user.get("last_name")) if x)
        changed = new or rec.get("username") != (user.get("username") or "") or rec.get("name") != name or rec.get("blocked")
        rec["username"] = user.get("username", "") or ""
        rec["name"] = name
        rec["blocked"] = False
        rec.setdefault("guilds", []); rec.setdefault("banned", False)
        if changed:
            self._save()
        return rec

    # ------------------------------------------------------------------ telegram http
    async def _http_post(self, method, payload, timeout=40):
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=timeout + 10)
        r = await self._client.post(f"https://api.telegram.org/bot{self.token}/{method}", json=payload, timeout=timeout)
        return r.json()

    async def call(self, method, **payload):
        try:
            return await self._post(method, payload)
        except Exception as e:
            print(f"[TG] {method} failed: {e}")
            return None

    @staticmethod
    def _extras_error(res):
        d = str((res or {}).get("description", "")).lower()
        return any(k in d for k in ("style", "icon", "custom emoji", "button"))

    async def show(self, chat_id, text, markup=None, msg_id=None):
        """Edit the message the user just pressed, or send a new one."""
        p = {"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True}
        if markup:
            p["reply_markup"] = markup if self.fancy else plain(markup)
        for attempt in range(2):
            q = dict(p)
            res = None
            if msg_id:
                q["message_id"] = msg_id
                res = await self.call("editMessageText", **q)
                if res and res.get("ok"):
                    return res
                if res and "not modified" in str(res.get("description", "")).lower():
                    return res
                q.pop("message_id", None)
            res = await self.call("sendMessage", **q)
            if res and not res.get("ok") and markup and self.fancy and self._extras_error(res):
                self.fancy = False                       # Telegram refused colours/icons: continue with plain buttons
                p["reply_markup"] = plain(markup)
                continue
            return res

    # ------------------------------------------------------------------ identity / limits
    def is_owner(self, user) -> bool:
        if not user:
            return False
        if user.get("id") in OWNER_IDS:
            return True
        return str(user.get("username", "")).lower() in OWNER_USERNAMES

    def tier_of(self, user):
        """owner / premium / free  (premium is set by the owner with /premium ID [days])"""
        if self.is_owner(user):
            return "owner"
        rec = self._touch(user)
        until = float(rec.get("premium_until") or 0)
        if rec.get("premium") and (not until or until > time.time()):
            return "premium"
        return "free"

    def _tg_limit(self, tier="free"):
        try:
            return int(self.ad.tier_limits(tier)[0])
        except Exception:
            return 3 if tier != "premium" else 10

    def _buy_hint(self):
        return f"\n💎 Premium {self.ad.price} ৳ = 10 guilds × 8 bots. DM {self.ad.owner_tg} to buy."

    def _guild_allowed(self, user, gid):
        tier = self.tier_of(user)
        if tier == "owner":
            return ""
        rec = self._touch(user)
        if gid in rec["guilds"]:
            return ""
        lim = self._tg_limit(tier)
        if len(rec["guilds"]) >= lim:
            return (f"You already use <b>{len(rec['guilds'])}/{lim}</b> guilds on the <b>{tier.upper()}</b> plan."
                    + ("" if tier == "premium" else self._buy_hint()))
        return ""

    # ------------------------------------------------------------------ screens
    def menu_markup(self, owner):
        rows = [[btn("🟢 Add bots", "add", "success", icon=ICONS.get("add"))],
                [btn("🏰 My guilds", "my", "primary", icon=ICONS.get("my")), btn("📊 Live stats", "stats", "primary", icon=ICONS.get("stats"))],
                [btn("🏆 Top guilds", "top", "primary", icon=ICONS.get("top")), btn("ℹ️ Help", "help", "primary", icon=ICONS.get("help"))]]
        if owner:
            rows.append([btn("⚙️ Settings", "set", "primary"), btn("📢 Broadcast", "bc", "primary")])
            rows.append([btn("👥 Users", "users", "primary"), btn("📈 Status", "status", "primary")])
        rows.append([btn("💠 Owner " + OWNER_HANDLE, url="https://t.me/" + OWNER_HANDLE.lstrip("@"))])
        return kb(rows)

    def welcome(self, user):
        owner = self.is_owner(user)
        rec = self._touch(user)
        name = esc(" ".join(x for x in (user.get("first_name"), user.get("last_name")) if x) or "Player")
        tier = self.tier_of(user)
        role = {"owner": "👑 Owner", "premium": "💎 Premium"}.get(tier, "🆓 Free")
        if owner:
            lim_txt = "♾ unlimited"
            guilds_txt = "♾ unlimited"
        else:
            lim_txt = f"up to {self.ad.limit(tier)} per guild"
            guilds_txt = f"{len(rec['guilds'])}/{self._tg_limit(tier)}"
        return card("HASIB ✘ GLORY",
                    f"👤 Name: {name}", f"🆔 User ID: <code>{user['id']}</code>", f"🎖 Role: {role}",
                    f"🏰 Guilds: {guilds_txt}", f"🤖 Bots: {lim_txt}",
                    LINE,
                    "🌍 BD · IND · PK · TW and more", "⚡ HS MODE ON · squads play non-stop",
                    *([] if tier != "free" else [f"💎 Premium {self.ad.price} ৳: 10 guilds × 8 bots · DM {self.ad.owner_tg}"]))

    def guild_line(self, r, lim=None):
        name = esc(r["name"]) if r.get("name") else "Guild"
        lvl = f"⭐ Lv {r['level']}" if r.get("level") else "⭐ Lv -"
        reg = r.get("region") or "-"
        return (f"🏰 <b>{name}</b>\n"
                f"├─ 🆔 <code>{esc(r['guild_id'])}</code>\n"
                f"├─ {FLAGS.get(reg, '🌍')} Region: {esc(reg)}  ·  {lvl}\n"
                f"├─ 🤖 Bots: {r['bots']}/{lim or self.ad.limit()} ({r.get('online', 0)} online)\n"
                f"└─ ✨ EXP farmed: {int(r.get('exp_gained', 0)):,}")

    # ------------------------------------------------------------------ updates
    async def handle_update(self, u):
        if "message" in u:
            await self.on_message(u["message"])
        elif "callback_query" in u:
            await self.on_callback(u["callback_query"])

    def _blocked(self, user):
        rec = self._touch(user)
        return rec.get("banned") and not self.is_owner(user)

    async def on_message(self, m):
        chat = m.get("chat", {})
        user = m.get("from") or {}
        if chat.get("type") != "private" or not user.get("id"):
            return
        cid = chat["id"]
        if self._blocked(user):
            return await self.show(cid, "🚫 You are blocked from this bot.")
        text = (m.get("text") or "").strip()
        owner = self.is_owner(user)
        if text.startswith("/"):
            cmd, _, arg = text.partition(" ")
            return await self.on_command(cid, user, owner, cmd.split("@")[0].lower(), arg.strip())
        ses = self.sessions.get(cid)
        step = ses.get("step") if ses else None
        if step == "guild":
            return await self.take_guild(cid, user, text)
        if step == "custom" and owner:
            if text.isdigit() and 1 <= int(text) <= 500:
                ses["count"] = int(text)
                return await self.confirm(cid, owner)
            return await self.show(cid, "Send a number from 1 to 500.", kb([[btn("🔴 Cancel", "cancel", "danger")]]))
        if step == "bc_text" and owner:
            return await self.bc_preview(cid, text)
        await self.show(cid, self.welcome(user), self.menu_markup(owner))

    async def on_command(self, cid, user, owner, cmd, arg):
        if cmd in ("/start", "/menu"):
            self.sessions.pop(cid, None)
            return await self.show(cid, self.welcome(user), self.menu_markup(owner))
        if cmd == "/help":
            return await self.on_callback_data(cid, user, owner, "help", None)
        if cmd == "/add":
            return await self.ask_guild(cid)
        if cmd == "/cancel":
            self.sessions.pop(cid, None)
            return await self.show(cid, "🔴 Cancelled.", self.menu_markup(owner))
        if cmd in ("/myguilds", "/my"):
            return await self.my_guilds(cid, user, owner)
        if cmd == "/stats":
            return await self.stats(cid)
        if cmd == "/top":
            return await self.top(cid)
        if cmd == "/guild":
            return await self.one_guild(cid, user, owner, arg)
        if not owner:
            return await self.show(cid, "🚫 That command is for the owner only.", self.menu_markup(False))
        # ---------------- owner commands
        if cmd == "/status":
            return await self.status(cid)
        if cmd == "/users":
            return await self.users_view(cid)
        if cmd in ("/broadcast", "/boardcast", "/bc"):
            if arg:
                return await self.bc_preview(cid, arg)
            return await self.bc_ask(cid)
        if cmd in ("/premium", "/unpremium"):
            parts = arg.split()
            if not parts or not parts[0].isdigit():
                return await self.show(cid, "Use: <code>/premium TELEGRAM_ID [days]</code> or <code>/unpremium TELEGRAM_ID</code>", self.menu_markup(True))
            uid_ = parts[0]
            rec = self.users.setdefault(uid_, {"username": "", "name": "", "guilds": [], "banned": False, "blocked": False, "first": int(time.time())})
            if cmd == "/premium":
                days = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
                rec["premium"] = True; rec["premium_until"] = (time.time() + days * 86400) if days else 0
                self._save()
                return await self.show(cid, f"💎 {uid_} is now <b>PREMIUM</b>" + (f" for {days} days" if days else " (no expiry)"), self.menu_markup(True))
            rec["premium"] = False; rec["premium_until"] = 0; self._save()
            return await self.show(cid, f"🆓 {uid_} is back to FREE", self.menu_markup(True))
        if cmd == "/limit" and arg.isdigit():
            return await self.apply(cid, {"max_per_guild": int(arg)})
        if cmd == "/tglimit" and arg.isdigit():
            return await self.apply(cid, {"tg_guilds_per_user": int(arg)})
        if cmd == "/autogen" and arg.lower() in ("on", "off"):
            return await self.apply(cid, {"auto_gen": arg.lower() == "on"})
        _flags = {"/cs": "cs_mode", "/br": "br_mode", "/fast": "fast_mode", "/bio": "auto_bio", "/friend": "auto_friend", "/csrank": "cs_rank", "/cssquad": "cs_squad"}
        if cmd in _flags and arg.lower() in ("on", "off"):
            return await self.apply(cid, {_flags[cmd]: arg.lower() == "on"})
        if cmd == "/prefix":
            parts = arg.split()
            if parts:
                body = {"name_prefix": parts[0]}
                if len(parts) >= 2:
                    body["pass_prefix"] = parts[1]
                return await self.apply(cid, body)
        if cmd == "/remove" and arg.isdigit():
            n = self.ad.remove_guild(arg)
            return await self.show(cid, f"🔴 Removed <b>{n}</b> bot(s) from guild <code>{esc(arg)}</code>.", self.menu_markup(True))
        if cmd in ("/ban", "/unban") and arg.isdigit():
            rec = self.users.get(arg)
            if not rec:
                return await self.show(cid, "User not found.", self.menu_markup(True))
            rec["banned"] = cmd == "/ban"
            self._save()
            return await self.show(cid, ("🚫 Banned " if cmd == "/ban" else "🟢 Unbanned ") + f"<code>{esc(arg)}</code>", self.menu_markup(True))
        await self.show(cid, card("OWNER COMMANDS", "/status  /users  /broadcast TEXT", "/limit N  /tglimit N", "/autogen on|off",
                                  "/premium ID [days]  /unpremium ID", "/cs on|off  /br on|off  /fast on|off", "/csrank on|off  /cssquad on|off", "/bio on|off  /friend on|off",
                                  "/prefix NAME PASS", "/remove GUILD_ID", "/ban ID  /unban ID"), self.menu_markup(True))

    async def on_callback(self, q):
        user = q.get("from") or {}
        msg = q.get("message") or {}
        cid = (msg.get("chat") or {}).get("id")
        await self.call("answerCallbackQuery", callback_query_id=q.get("id"))
        if cid is None or not user.get("id") or (msg.get("chat") or {}).get("type") != "private":
            return
        if self._blocked(user):
            return await self.show(cid, "🚫 You are blocked from this bot.")
        await self.on_callback_data(cid, user, self.is_owner(user), q.get("data", ""), msg.get("message_id"))

    async def on_callback_data(self, cid, user, owner, data, mid):
        ses = self.sessions.get(cid)
        if data == "home":
            self.sessions.pop(cid, None)
            return await self.show(cid, self.welcome(user), self.menu_markup(owner), mid)
        if data == "cancel":
            self.sessions.pop(cid, None)
            return await self.show(cid, "🔴 Cancelled.", self.menu_markup(owner), mid)
        if data == "help":
            txt = card("HOW IT WORKS", "1️⃣ Press 🟢 Add bots", "2️⃣ Send your guild ID", "3️⃣ Pick a region", "4️⃣ Pick how many bots",
                       "5️⃣ Press 🟢 Start", LINE, "🤖 Bots join your guild and play squad matches to farm EXP.",
                       "🏰 /myguilds shows your guilds, 📊 /stats the live numbers.")
            return await self.show(cid, txt, kb([[btn("⬅️ Back", "home", "primary")]]), mid)
        if data == "add":
            return await self.ask_guild(cid, mid)
        if data == "my":
            return await self.my_guilds(cid, user, owner, mid)
        if data == "stats":
            return await self.stats(cid, mid)
        if data == "top":
            return await self.top(cid, mid)
        if data.startswith("g:"):
            return await self.one_guild(cid, user, owner, data[2:], mid)
        if data.startswith("rm:"):
            return await self.remove_ask(cid, user, owner, data[3:], mid)
        if data.startswith("rmy:"):
            return await self.remove_go(cid, user, owner, data[4:], mid)
        if owner:
            if data == "status":
                return await self.status(cid, mid)
            if data == "users":
                return await self.users_view(cid, mid)
            if data == "set":
                return await self.settings_view(cid, mid)
            if data.startswith("set:"):
                return await self.settings_change(cid, data[4:], mid)
            if data == "bc":
                return await self.bc_ask(cid, mid)
            if data == "bcgo":
                return await self.bc_go(cid, mid)
        if not ses:
            return await self.show(cid, self.welcome(user), self.menu_markup(owner), mid)
        if data.startswith("reg:"):
            reg = data[4:]
            if reg not in self.ad.regions():
                return
            ses["region"] = reg
            ses["step"] = "count"
            return await self.ask_count(cid, owner, mid)
        if data == "cnt:custom" and owner:
            ses["step"] = "custom"
            return await self.show(cid, "✏️ Send the number of bots (1 to 500).", kb([[btn("🔴 Cancel", "cancel", "danger")]]), mid)
        if data.startswith("cnt:"):
            try:
                ses["count"] = int(data[4:])
            except ValueError:
                return
            return await self.confirm(cid, owner, mid)
        if data.startswith("src:") and owner:
            if data[4:] in ("auto", "create"):
                ses["source"] = data[4:]
            return await self.confirm(cid, owner, mid)
        if data == "go":
            return await self.go(cid, user, owner, mid)

    # ------------------------------------------------------------------ add bots flow
    async def ask_guild(self, cid, mid=None):
        self.sessions[cid] = {"step": "guild", "source": "auto"}
        await self.show(cid, card("ADD BOTS", "🏰 Send your guild ID", "🔢 Numbers only (5 to 15 digits)"),
                        kb([[btn("🔴 Cancel", "cancel", "danger")]]), mid)

    async def take_guild(self, cid, user, text):
        ses = self.sessions[cid]
        if not (text.isdigit() and 5 <= len(text) <= 15):
            return await self.show(cid, "❌ A guild ID is 5 to 15 digits. Send it again.", kb([[btn("🔴 Cancel", "cancel", "danger")]]))
        err = self._guild_allowed(user, text)
        if err:
            self.sessions.pop(cid, None)
            return await self.show(cid, "❌ " + err, self.menu_markup(self.is_owner(user)))
        ses["guild"] = text
        ses["tier"] = self.tier_of(user)
        ses["step"] = "region"
        rows, row = [], []
        for r in self.ad.regions():
            row.append(btn(f"{FLAGS.get(r, '🌍')} {r}", f"reg:{r}", "primary"))
            if len(row) == 3:
                rows.append(row)
                row = []
        if row:
            rows.append(row)
        rows.append([btn("🔴 Cancel", "cancel", "danger")])
        await self.show(cid, card("PICK REGION", f"🏰 Guild: <code>{esc(text)}</code>", "🌍 Choose the region"), kb(rows))

    async def ask_count(self, cid, owner, mid):
        ses = self.sessions[cid]
        row = [btn(f"🤖 {n}", f"cnt:{n}", "success") for n in self.ad.choices(self.sessions.get(cid, {}).get("tier", "free"))]
        rows = [row[i:i + 4] for i in range(0, len(row), 4)]
        if owner:
            rows.append([btn("✏️ Custom amount", "cnt:custom", "primary")])
        rows.append([btn("🔴 Cancel", "cancel", "danger")])
        await self.show(cid, card("HOW MANY BOTS", f"🏰 Guild: <code>{esc(ses['guild'])}</code>",
                                  f"{FLAGS.get(ses['region'], '🌍')} Region: {ses['region']}"), kb(rows), mid)

    async def confirm(self, cid, owner, mid=None):
        ses = self.sessions[cid]
        ses["step"] = "confirm"
        src = ses.get("source", "auto") if owner else "auto"
        src_txt = "🤖 Auto (ready accounts first, then new ones)" if src == "auto" else "🛠 Create new accounts"
        lines = [f"🏰 Guild: <code>{esc(ses['guild'])}</code>", f"{FLAGS.get(ses['region'], '🌍')} Region: {ses['region']}",
                 f"🤖 Bots: <b>{ses['count']}</b>"]
        if owner:
            lines.append(f"📦 Accounts: {src_txt}")
        rows = []
        if owner:
            rows.append([btn(("✅ " if src == "auto" else "") + "🤖 Auto", "src:auto", "primary"),
                         btn(("✅ " if src == "create" else "") + "🛠 Create new", "src:create", "primary")])
        rows.append([btn("🟢 Start", "go", "success"), btn("🔴 Cancel", "cancel", "danger")])
        await self.show(cid, card("CONFIRM", *lines), kb(rows), mid)

    async def go(self, cid, user, owner, mid):
        ses = self.sessions.get(cid)
        if not ses or ses.get("step") != "confirm":
            return
        err = self._guild_allowed(user, ses["guild"])
        if err:
            self.sessions.pop(cid, None)
            return await self.show(cid, "❌ " + err, self.menu_markup(owner), mid)
        res = await self.ad.add_bots(ses["guild"], ses["region"], ses["count"], ses.get("source", "auto") if owner else "auto", owner, ses.get("tier", "free"))
        self.sessions.pop(cid, None)
        if not res.get("ok"):
            return await self.show(cid, "❌ " + esc(res.get("error", "Failed")), self.menu_markup(owner), mid)
        if not owner:
            rec = self._touch(user)
            if ses["guild"] not in rec["guilds"]:
                rec["guilds"].append(ses["guild"])
            self._save()
        lines = [f"🏰 Guild: <code>{esc(res['guild_id'])}</code>",
                 f"{FLAGS.get(res['region'], '🌍')} Region: {res['region']}",
                 f"🤖 Bots starting: <b>{res['added']}</b>",
                 f"📊 Guild now: {res['in_guild']}" + ("" if owner else f"/{res.get('max', self.ad.limit())}")]
        if res.get("created"):
            lines.append(f"🛠 {res['created']} new account(s) are being created (20 to 30 seconds each)")
        if res.get("short"):
            lines.append(f"⚠️ {res['short']} short (not enough accounts)")
        lines.append("⚡ They play squad matches non-stop")
        await self.show(cid, card("BOTS STARTED", *lines), kb([[btn("🏰 My guilds", "my", "primary"), btn("🟢 Add more", "add", "success")],
                                                              [btn("⬅️ Menu", "home", "primary")]]), mid)

    # ------------------------------------------------------------------ guild views
    def _rows_for(self, user, owner):
        rows = self.ad.guild_rows()
        if owner:
            return rows
        mine = set(self._touch(user)["guilds"])
        return [r for r in rows if r["guild_id"] in mine]

    async def my_guilds(self, cid, user, owner, mid=None):
        rows = self._rows_for(user, owner)
        if not rows:
            txt = card("MY GUILDS", "🏰 No guilds yet.", "Press 🟢 Add bots to start.")
            markup = kb([[btn("🟢 Add bots", "add", "success")], [btn("⬅️ Back", "home", "primary")]])
        else:
            title = "ALL GUILDS" if owner else "MY GUILDS"
            _lim = self.ad.limit(self.tier_of(user))
            txt = card(title, *[self.guild_line(r, _lim) + "\n" for r in rows[:10]])
            buttons = [btn(f"🏰 {r['name'] or r['guild_id']}"[:28], f"g:{r['guild_id']}", "primary") for r in rows[:10]]
            markup = kb([buttons[i:i + 2] for i in range(0, len(buttons), 2)] +
                        [[btn("🟢 Add bots", "add", "success"), btn("🔄 Refresh", "my", "primary")], [btn("⬅️ Back", "home", "primary")]])
        await self.show(cid, txt, markup, mid)

    async def one_guild(self, cid, user, owner, gid, mid=None):
        rows = {r["guild_id"]: r for r in self._rows_for(user, owner)}
        if gid not in rows:
            return await self.show(cid, "Guild not found in your list.", self.menu_markup(owner), mid)
        await self.show(cid, card("GUILD INFO", self.guild_line(rows[gid], self.ad.limit(self.tier_of(user)))),
                        kb([[btn("🔄 Refresh", f"g:{gid}", "primary"), btn("🔴 Remove bots", f"rm:{gid}", "danger")],
                            [btn("⬅️ Back", "my", "primary")]]), mid)

    async def remove_ask(self, cid, user, owner, gid, mid):
        rows = {r["guild_id"]: r for r in self._rows_for(user, owner)}
        if gid not in rows:
            return await self.show(cid, "Guild not found in your list.", self.menu_markup(owner), mid)
        await self.show(cid, card("REMOVE BOTS?", f"🏰 Guild: <code>{esc(gid)}</code>", f"🤖 {rows[gid]['bots']} bot(s) will stop and leave"),
                        kb([[btn("🔴 Yes, remove", f"rmy:{gid}", "danger"), btn("🟢 Keep", f"g:{gid}", "success")]]), mid)

    async def remove_go(self, cid, user, owner, gid, mid):
        rows = {r["guild_id"]: r for r in self._rows_for(user, owner)}
        if gid not in rows:
            return await self.show(cid, "Guild not found in your list.", self.menu_markup(owner), mid)
        n = self.ad.remove_guild(gid)
        if not owner:
            rec = self._touch(user)
            if gid in rec["guilds"]:
                rec["guilds"].remove(gid)
                self._save()
        await self.show(cid, card("REMOVED", f"🔴 {n} bot(s) removed from <code>{esc(gid)}</code>", "The slot is free again."),
                        self.menu_markup(owner), mid)

    async def stats(self, cid, mid=None):
        t = self.ad.totals()
        up = int(t.get("uptime", 0))
        up_txt = f"{up // 3600}h {up % 3600 // 60}m"
        txt = card("LIVE STATS", f"🏰 Guilds: <b>{t['guilds']}</b>", f"🤖 Bots: <b>{t['bots']}</b> ({t.get('online', 0)} online)",
                   f"✨ EXP farmed: <b>{int(t['exp']):,}</b>", f"🎮 Matches: <b>{int(t['matches']):,}</b>", f"⏱ Uptime: {up_txt}",
                   "⚡ HS MODE: ON")
        await self.show(cid, txt, kb([[btn("🔄 Refresh", "stats", "primary"), btn("🏆 Top guilds", "top", "primary")],
                                      [btn("⬅️ Back", "home", "primary")]]), mid)

    async def top(self, cid, mid=None):
        rows = sorted(self.ad.guild_rows(), key=lambda r: -int(r.get("exp_gained", 0)))[:10]
        medals = ["🥇", "🥈", "🥉"] + ["🔹"] * 7
        if not rows:
            lines = ["No guilds yet."]
        else:
            lines = [f"{medals[i]} <b>{esc(r['name'] or r['guild_id'])}</b> · {FLAGS.get(r.get('region'), '🌍')} {esc(r.get('region') or '-')} · "
                     f"Lv {r.get('level') or '-'} · ✨ {int(r.get('exp_gained', 0)):,}" for i, r in enumerate(rows)]
        await self.show(cid, card("TOP GUILDS", *lines), kb([[btn("🔄 Refresh", "top", "primary"), btn("⬅️ Back", "home", "primary")]]), mid)

    # ------------------------------------------------------------------ owner tools
    async def status(self, cid, mid=None):
        t = self.ad.totals()
        pool = self.ad.pool()
        pool_txt = "  ".join(f"{FLAGS.get(r, '')} {r} {v['free']:,}" for r, v in pool.items())
        txt = card("OWNER STATUS", f"🏰 Guilds: <b>{t['guilds']}</b>", f"🤖 Bots: <b>{t['bots']}</b> ({t.get('online', 0)} online)",
                   f"✨ EXP farmed: <b>{int(t['exp']):,}</b>", f"🎮 Matches: <b>{int(t['matches']):,}</b>", LINE,
                   f"📦 Ready accounts", pool_txt, LINE, f"👥 Telegram users: {len(self.users)}")
        await self.show(cid, txt, kb([[btn("⚙️ Settings", "set", "primary"), btn("📢 Broadcast", "bc", "primary")],
                                      [btn("⬅️ Back", "home", "primary")]]), mid)

    async def users_view(self, cid, mid=None):
        total = len(self.users)
        banned = sum(1 for u in self.users.values() if u.get("banned"))
        blocked = sum(1 for u in self.users.values() if u.get("blocked"))
        with_guilds = sum(1 for u in self.users.values() if u.get("guilds"))
        await self.show(cid, card("USERS", f"👥 Total: <b>{total}</b>", f"🏰 With guilds: {with_guilds}", f"🚫 Banned: {banned}",
                                  f"⛔ Blocked the bot: {blocked}", "Ban: /ban ID   Unban: /unban ID"),
                        kb([[btn("📢 Broadcast", "bc", "primary"), btn("⬅️ Back", "home", "primary")]]), mid)

    async def settings_view(self, cid, mid=None):
        s = self.ad.settings()
        txt = card("SETTINGS", f"🤖 Bot limit per guild (users): <b>{s['max_per_guild']}</b>",
                   f"🏰 Guilds per Telegram user: <b>{s['tg_guilds_per_user']}</b>",
                   f"🛠 Auto-create accounts: <b>{'ON' if s['auto_gen'] else 'OFF'}</b>",
                   f"⚔️ Clash Squad (CS): <b>{'ON' if s.get('cs_mode') else 'OFF'}</b>   🪂 Battle Royale (BR): <b>{'ON' if s.get('br_mode') else 'OFF'}</b>",
                   f"⚡ Fast switch: <b>{'ON' if s.get('fast_mode') else 'OFF'}</b>   📝 Auto bio: <b>{'ON' if s.get('auto_bio') else 'OFF'}</b>   🤝 Auto friend: <b>{'ON' if s.get('auto_friend') else 'OFF'}</b>",
                   f"🏷 Nickname prefix: <code>{esc(s['name_prefix'])}</code>", f"🔑 Password prefix: <code>{esc(s['pass_prefix'])}</code>",
                   LINE, "Prefixes: /prefix NAME PASS")
        rows = [[btn("➖ Bot limit", "set:lim-", "danger"), btn("➕ Bot limit", "set:lim+", "success")],
                [btn("➖ Guilds/user", "set:tg-", "danger"), btn("➕ Guilds/user", "set:tg+", "success")],
                [btn(("🟢 Auto-create ON" if s["auto_gen"] else "🔴 Auto-create OFF"), "set:autogen", "success" if s["auto_gen"] else "danger")],
                [btn(("🟢 CS ON" if s.get("cs_mode") else "🔴 CS OFF"), "set:cs", "success" if s.get("cs_mode") else "danger"),
                 btn(("🟢 BR ON" if s.get("br_mode") else "🔴 BR OFF"), "set:br", "success" if s.get("br_mode") else "danger")],
                [btn(("🟢 Fast ON" if s.get("fast_mode") else "🔴 Fast OFF"), "set:fast", "success" if s.get("fast_mode") else "danger"),
                 btn(("🟢 Bio ON" if s.get("auto_bio") else "🔴 Bio OFF"), "set:bio", "success" if s.get("auto_bio") else "danger"),
                 btn(("🟢 Friend ON" if s.get("auto_friend") else "🔴 Friend OFF"), "set:friend", "success" if s.get("auto_friend") else "danger")],
                [btn("⬅️ Back", "home", "primary")]]
        await self.show(cid, txt, kb(rows), mid)

    async def settings_change(self, cid, what, mid):
        s = self.ad.settings()
        body = {}
        if what == "lim+": body = {"max_per_guild": s["max_per_guild"] + 1}
        elif what == "lim-": body = {"max_per_guild": max(1, s["max_per_guild"] - 1)}
        elif what == "tg+": body = {"tg_guilds_per_user": s["tg_guilds_per_user"] + 1}
        elif what == "tg-": body = {"tg_guilds_per_user": max(1, s["tg_guilds_per_user"] - 1)}
        elif what == "autogen": body = {"auto_gen": not s["auto_gen"]}
        elif what in ("cs", "br", "fast", "bio", "friend", "csrank", "cssquad"):
            _k = {"cs": "cs_mode", "br": "br_mode", "fast": "fast_mode", "bio": "auto_bio", "friend": "auto_friend",
                  "csrank": "cs_rank", "cssquad": "cs_squad"}[what]
            body = {_k: not s.get(_k)}
        if body:
            res = self.ad.apply_settings(body)
            if not res.get("ok"):
                await self.call("sendMessage", chat_id=cid, text="❌ " + str(res.get("error")))
        await self.settings_view(cid, mid)

    async def apply(self, cid, body):
        res = self.ad.apply_settings(body)
        if not res.get("ok"):
            return await self.show(cid, "❌ " + esc(res.get("error", "Failed")), self.menu_markup(True))
        await self.settings_view(cid)

    # ------------------------------------------------------------------ broadcast (owner)
    async def bc_ask(self, cid, mid=None):
        self.sessions[cid] = {"step": "bc_text"}
        await self.show(cid, card("BROADCAST", "📢 Send the message you want to send", "to every Telegram user of this bot."),
                        kb([[btn("🔴 Cancel", "cancel", "danger")]]), mid)

    async def bc_preview(self, cid, text):
        text = text.strip()
        if not text:
            return await self.bc_ask(cid)
        if len(text) > 3500:
            return await self.show(cid, "❌ Too long (max 3500 characters).", kb([[btn("🔴 Cancel", "cancel", "danger")]]))
        self.sessions[cid] = {"step": "bc_confirm", "text": text}
        targets = sum(1 for u in self.users.values() if not u.get("blocked") and not u.get("banned"))
        await self.show(cid, card("PREVIEW", esc(text), LINE, f"👥 Will be sent to {targets} user(s)"),
                        kb([[btn("🟢 Send now", "bcgo", "success"), btn("🔴 Cancel", "cancel", "danger")]]))

    async def bc_go(self, cid, mid):
        ses = self.sessions.get(cid)
        if not ses or ses.get("step") != "bc_confirm":
            return
        text = ses["text"]
        self.sessions.pop(cid, None)
        await self.show(cid, card("BROADCAST", "📤 Sending..."), None, mid)
        asyncio.create_task(self._broadcast(cid, text))

    async def _broadcast(self, owner_cid, text):
        body = card("ANNOUNCEMENT", esc(text))
        ok = fail = blocked = 0
        for uid, rec in list(self.users.items()):
            if rec.get("banned") or rec.get("blocked"):
                continue
            res = await self.call("sendMessage", chat_id=int(uid), text=body, parse_mode="HTML", disable_web_page_preview=True)
            if res and res.get("ok"):
                ok += 1
            else:
                code = (res or {}).get("error_code")
                if code in (400, 403):
                    rec["blocked"] = True
                    blocked += 1
                else:
                    fail += 1
            await asyncio.sleep(0.05)               # stay under Telegram's ~30 messages per second
        self._save()
        try:
            self.ad.log(f"[Telegram] Broadcast sent to {ok} user(s)", "success")
        except Exception:
            pass
        await self.show(owner_cid, card("BROADCAST DONE", f"🟢 Sent: {ok}", f"🔴 Failed: {fail}", f"⛔ Blocked the bot: {blocked}"),
                        self.menu_markup(True))


async def run(token, adapter, post=None, users_file=USERS_FILE):
    """Long polling with self-healing: network errors, webhook leftovers (409) and restarts never take the bot offline."""
    bot = TgBot(token, adapter, post=post, users_file=users_file)
    me = None; tries = 0
    while True:                                   # a failed getMe used to stop the bot for good
        me = await bot.call("getMe")
        if me and me.get("ok"): break
        if me and me.get("error_code") in (401, 404):
            adapter.state["enabled"] = False
            print("[TG] token rejected by Telegram (401) - check TG_BOT_TOKEN in main.py")
            return "bad_token"
        tries += 1
        print(f"[TG] getMe failed (try {tries}) - retrying")
        await asyncio.sleep(min(30, 3 * tries))
    adapter.state["enabled"] = True
    adapter.state["username"] = me["result"].get("username", "")
    print(f"[TG] bot online: @{adapter.state['username']}")
    await bot.call("deleteWebhook", drop_pending_updates=False)     # a leftover webhook blocks getUpdates (error 409)
    await bot.call("setMyCommands", commands=[
        {"command": "start", "description": "Open the menu"},
        {"command": "add", "description": "Add bots to a guild"},
        {"command": "myguilds", "description": "Your guilds"},
        {"command": "stats", "description": "Live stats"},
        {"command": "top", "description": "Top guilds"},
        {"command": "help", "description": "How it works"}])
    offset = 0; fails = 0
    try:
        while True:
            res = await bot.call("getUpdates", offset=offset, timeout=25, allowed_updates=["message", "callback_query"])
            if not res or not res.get("ok"):
                fails += 1
                code = (res or {}).get("error_code")
                if code == 409:
                    print("[TG] 409 conflict - another copy of this bot is polling (or a webhook). Clearing webhook...")
                    await bot.call("deleteWebhook", drop_pending_updates=False)
                if code == 401:
                    print("[TG] token revoked"); return "bad_token"
                await asyncio.sleep(min(20, 2 + fails))
                continue
            fails = 0
            for u in res.get("result", []):
                offset = u["update_id"] + 1
                try:
                    await bot.handle_update(u)
                except Exception:
                    traceback.print_exc()
    finally:
        adapter.state["enabled"] = False
