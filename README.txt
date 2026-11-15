OWNER : HASIB Coder | FF UID 2799233875 | TG @hasib_hii (DM to buy) | TT @hasib_hi | YT @hasib_hi
PLANS : FREE = 3 guilds x 4 bots | PREMIUM 400 TK = 10 guilds x 8 bots     (details: OWNER.txt)

HASIB X GLORY V5  -  Web panel + Telegram bot in ONE program
=============================================================
Run:    pip install -r requirements.txt
        python main.py
Panel:  http://localhost:25567   (if the port is busy it uses the next free one; hosting panels' PORT is used automatically)

WHAT IS NEW IN V5
-----------------
CS (Clash Squad)   Owner: web panel -> Settings -> "Match modes" -> CS ON/OFF and BR ON/OFF (also Telegram: /cs on|off, /br on|off).
                   CS only / BR only / both (squads alternate CS, BR, CS...) / both off (bots wait). Bots follow within seconds.
                   CS uses the CS matchmaking packet and the CS movement packet from the tested CS build.
FAST SWITCH        In CS mode the next match is searched right after a match ends (no parking, no waiting for the other 3 bots).
                   Switch: Settings -> "Fast match switching" (Telegram: /fast on|off). Tunables at the top of main.py.
TELEGRAM TOKEN     Open main.py, find  TG_BOT_TOKEN = ""  at the top, paste the @BotFather token, run. Web on = Telegram bot on.
AUTO FRIEND        Bots accept friend requests on both connections. Fixed a V4 bug: the accept used int(DEV_UID) with DEV_UID = ""
                   which crashed, so nothing was ever accepted.
AUTO BIO           Every bot writes OWNER_BIO into its Bio after login and then reads the profile back to verify (see log lines "BIO set").
ALL REGIONS        Ready-account files may now be named after any region (accounts-ME.json, br_ids.txt ...). Every region is accepted.
LEVEL UP           Bots gain EXP/level by playing; a "LEVEL UP" line is logged and the level shows in the panel.
LOGIN / WEB FIXES  * main.py now switches to its own folder (panel + accounts files were not found when started from elsewhere)
                   * port busy -> next port instead of silently quitting; PORT env var supported
                   * Play-Store version lookup was blocking the whole server on every login -> now cached + non-blocking
                   * version server lookup retries 3 times
                   * UDP code works on Python 3.10 / 3.11 / 3.12 (V4 used loop.sock_sendto which needs 3.11+)
                   * login endpoint accepts JSON or form posts, 10 wrong tries/min instead of 6

NEEDS YOUR INPUT (not possible without packets from your own game client)
------------------------------------------------------------------------
CHARACTER / SKILL / GUN AUTO-EQUIP   equip_packets.json is the hook. Capture the packet (or HTTP call) your client sends when you
                   equip a character / skill / gun, paste it in the file, set "enabled": true. $UID = the bot's account id.
                   It is sent once after each login. Buying or picking guns INSIDE a CS round travels over UDP; that needs its own capture.
BIO ENDPOINT      BIO_ENDPOINT / BIO_FIELDS near the top of the "BIO" section in main.py were written from the usual FF social API shape
                   and could not be tested here. If the log says "BIO ... profile bio is ''", adjust those two lines.

LOGIN (password only, capital letters do not matter)
          user  : hasibxglory   -> guild info only
          owner : hasib10       -> everything, settings, upload, edit, delete
          Change in main.py -> LOGIN_PASSWORDS

Everything else (add bots, squads, Telegram menus, guest_ids/, config.json) works as in V4. See the V4 notes in the panel.


=====================  V5.1 UPDATE  =====================
TELEGRAM BOT ONLINE   The bot now heals itself: getMe is retried (it used to give up after one network hiccup), a leftover webhook is
                      deleted, 409 "conflict" is handled, and a supervisor restarts the polling loop if it ever dies.
                      Only a rejected token stops it. Token: main.py -> TG_BOT_TOKEN = "...". Run ONE copy only (two copies = 409).
CHARACTER / EMOTE     main.py -> CHARACTER_ID = 102000037, PROFILE_ITEM_ID = 102000037, EMOTE_ID = 909042007.
                      * Emote 909042007 is equipped after every login with the real ChooseEmote request taken from the CS project.
                      * Character and profile item: the request format is NOT in any of your files. Paste the request your game client
                        sends into equip_packets.json (character_request / profile_request). $CHARACTER_ID / $ITEM_ID are filled in.
GROUP GREETING        When a player enters the bot's group the bot plays emote 909042007 on him and writes the welcome lines in the
                      group chat (features, free trial, paid, owner HASIB Coder, YT / TT / TG). The same emote plays when a match is found.
                      Edit the texts: main.py -> WELCOME_MESSAGES, BRAND_NAME, YT_NAME, TT_NAME, TG_NAME.
START PAGE            The page before login now shows features, plans and prices, "Start now" and "Get free trial".
                      !! The prices (150 / 400 / 900) are EXAMPLES. Edit PLANS at the top of the script in hasib_coder_panel/index.html.

HOSTING (Railway / Render / any Docker host)
  Files added: Dockerfile, Procfile, railway.json, render.yaml, runtime.txt, .env.example
  RAILWAY : New Project -> Deploy from GitHub (or "railway up") -> Variables: TG_BOT_TOKEN (optional) and DATA_DIR=/data
            -> add a Volume mounted at /data -> Settings -> Networking -> Generate Domain. Health check is /api/ping.
  RENDER  : New -> Blueprint (uses render.yaml) or New Web Service -> Docker. Add env TG_BOT_TOKEN. Use a paid plan with the Disk
            (mount /var/data, DATA_DIR=/var/data). The free plan sleeps after 15 minutes, so the bots would go offline.
  Without a volume the config, sessions and generated accounts are erased at every deploy.
  The web panel and the Telegram bot run inside the same process, one start command: python main.py


=====================  V5.2  FREE / PREMIUM  =====================
FREE     3 guilds, 4 bots per guild.            PREMIUM (400 tk)  10 guilds, 8 bots per guild.   Owner: unlimited.
Telegram : owner gives Premium with  /premium TELEGRAM_ID [days]  and removes it with  /unpremium TELEGRAM_ID.
Web      : (replaced in V5.3) User login = name + hasibxglory or a premium password the owner creates; Admin login = hasib10.
           The web quota is counted per NAME in tier_usage.json (V5.3).
           Free users who hit a limit are told how to buy Premium (DM @hasib_hii).
Limits   : main.py -> FREE_MAX_GUILDS, FREE_BOTS_PER_GUILD, PREMIUM_MAX_GUILDS, PREMIUM_BOTS_PER_GUILD, PREMIUM_PRICE_TK.
           The old "bots per guild" box in owner Settings no longer changes the plan limits.
BIO      : every bot writes the owner bio letter by letter with spaces (OWNER, FF UID, Telegram; TikTok/YouTube if BIO_MAX_LEN is raised).
START PAGE: shows the Free and Premium plans (400 TK), owner FF UID and the Telegram / TikTok / YouTube links.


=====================  V5.3  LOGIN / PREMIUM / DESIGN  =====================
LOGIN ENGINE       login_engine.py (+ Pb2/) is your working login. main.py tries its own login first; when that fails it tries
                   login_engine.py automatically. After 2 engine wins in a row the engine is tried first.
                   LOGIN_ENGINE=0 turns the fallback off, LOGIN_ENGINE_FIRST=1 always tries it first,
                   FF_APP_VERSION=1.xxx.x forces the game version if the Play Store lookup is blocked on your host.
                   The reason of every failed login is printed ("LOGIN FAILED ... HTTP 4xx / token rejected / MajorLogin rejected").
WEB LOGIN          Two tabs. User = name + password (free: hasibxglory, or a premium password). Admin = password only (hasib10).
                   Quotas (3 guilds x 4 bots free, 10 guilds x 8 bots premium) are now counted per NAME, not per IP.
                   Owner -> "Users & Premium": user count, user list, create / delete premium passwords (with days).
BIO                Coloured: O W N E R  Y O U T U B E  @h a s i b _ h i i   (main.py -> BIO_YT_HANDLE, BIO_COLORS).
CS RANK            Settings -> "CS Rank mode" (Telegram /csrank on|off). Put the RANKED Clash Squad search packet you captured
                   (plain protobuf hex, same format as the CS packet in main.py) into  cs_rank_packet.hex . Without that file the bots
                   search normal CS and the log says so.
CS SQUAD           Settings -> "CS in squads of 4" (Telegram /cssquad on|off). Experimental: the squad leader sends the CS search.
                   Default is solo CS (the tested way) with direct, immediate match start and fast switching.
DESIGN             The panel now uses the black + white glass "Crystal UI" look (Inter + JetBrains Mono, white buttons, spring motion).
START PAGE         Hero, features, how it works, Free / Premium plans (400 TK), owner FF UID, Telegram / TikTok / YouTube.
