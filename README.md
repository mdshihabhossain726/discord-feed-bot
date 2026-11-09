# RedditBridge

Discord bot that posts new, safe-for-work Reddit posts from subscribed subreddits into a Discord channel.
Each server configures itself with slash commands; data is isolated per server (`guild_id`).

> **Status:** core bot is written but has **not been run against live Discord/Reddit** yet. Follow the
> checklist below and report any errors. Dashboard, Alembic migrations, paid plans and owner admin
> panel are **not implemented yet**.

## Quickstart (5 steps)
1. **Discord:** https://discord.com/developers/applications → New Application → Bot → Reset Token (copy it).
   No privileged intents needed. Copy the Application ID too.
2. **Reddit:** log in → https://www.reddit.com/prefs/apps → create app (type *script*, redirect
   `http://localhost`). Copy client id (under the app name) and secret. Check Reddit's current Data API
   terms/approval requirements for your use.
3. **Configure:** `cp .env.example .env` and fill in the values.
4. **Run:**
   ```
   python3.12 -m venv .venv && source .venv/bin/activate
   pip install -r requirements.txt
   python -m app.run_bot
   ```
   The console prints an **Invite URL** — open it to add the bot to your server.
5. **In Discord:** `/setup #channel` → `/addsubreddit aww` → `/testfeed`.

Docker + PostgreSQL: add `POSTGRES_PASSWORD=...` to `.env`, then `docker compose up -d --build`.

## Commands
`/setup /setchannel /addsubreddit /removesubreddit /listsubreddits /setinterval /pause /resume /testfeed /status /settings /subscription /help`
Admin commands require **Manage Server** (checked server-side).

## Behavior notes
- Only posts created **after** you add a subreddit are sent (no backfill flood).
- NSFW subreddits are rejected; NSFW posts are never sent. Videos are sent as links.
- Duplicates are prevented by a unique (subscription, post) database row; failed sends retry up to 3 times.
- Removing the bot deletes that server's data.

## Tests
`pip install -r requirements-dev.txt && pytest`

## Security
Secrets live only in `.env` (git-ignored). Logs redact tokens. Never share your bot token; if leaked, reset it.
