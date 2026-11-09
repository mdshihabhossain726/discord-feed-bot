# RedditBridge

A Discord bot that posts new, safe-for-work posts from public subreddits into a Discord channel.
Each server configures itself with slash commands, and data is isolated per server (`guild_id`).

## Status

- **Tested on a live Discord server:** slash commands, PostgreSQL storage and sending messages to a channel.
- **Pending:** Reddit polling. New Reddit Data API apps need approval under Reddit's
  [Responsible Builder Policy](https://support.reddithelp.com/hc/en-us/articles/42728983564564-Responsible-Builder-Policy).
  An access request has been submitted. Until it is approved, `/addsubreddit` does not work.
- **Not implemented yet:** web dashboard, Alembic migrations, paid plans, owner admin panel.

## What it does (and does not do)

- Read-only: it never posts, comments, votes or messages on Reddit.
- Uses app-only OAuth and a descriptive User-Agent, and polls each subreddit at most every 5 minutes.
- Only public, SFW content: NSFW subreddits are rejected and NSFW posts are never sent. Videos are sent as links.
- Each Discord message links back to the original Reddit post.
- Stores only subreddit names, Reddit post IDs and delivery status. Post content is not stored,
  sold, or used to train AI models.
- Only posts created **after** a subreddit is added are sent (no backfill flood).
- Duplicates are prevented by a unique (subscription, post) database row. Failed sends retry up to 3 times.
- Removing the bot from a server deletes that server's data.

## Setup (Windows, VS Code, PostgreSQL)

1. **Database:** in pgAdmin run these one at a time:
   ```sql
   CREATE USER redditbridge WITH PASSWORD 'choose-a-password';
   CREATE DATABASE redditbridge OWNER redditbridge;
   ```
2. **Python (3.12 or 3.13):**
   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   ```
   If activation is blocked: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`
3. **Discord:** https://discord.com/developers/applications -> New Application -> Bot -> Reset Token.
   No privileged intents are needed. Copy the Application ID too.
4. **Reddit:** after your API access is approved, create an app (type *script*) at
   https://www.reddit.com/prefs/apps. The app name must not contain "reddit".
5. **Configure:** copy `.env.example` to `.env` and fill in the values. Never commit `.env`.
6. **Run:** `python -m app.run_bot`. The console prints an **Invite URL**; open it to add the bot to your server.
7. **In Discord:** `/setup #channel`, then `/testfeed`. Once Reddit access works: `/addsubreddit aww`.

Docker + PostgreSQL: add `POSTGRES_PASSWORD=...` to `.env`, then `docker compose up -d --build`.

## Commands

`/setup /setchannel /addsubreddit /removesubreddit /listsubreddits /setinterval /pause /resume /testfeed /status /settings /subscription /help`

Admin commands require **Manage Server** (checked server-side).

## Tests

`pip install -r requirements-dev.txt` then `pytest`

## Security

Secrets live only in `.env` (git-ignored). Logs redact tokens. Never share your bot token;
if it leaks, reset it in the Discord Developer Portal.
