# RedditBridge Architecture

## Process model
One Python process (Phase 1 default) runs three cooperating components on a single asyncio loop:

1. **FastAPI app**: dashboard, JSON API, Discord OAuth2 login, `/health`.
2. **discord.py client**: slash commands, guild join/leave events, message delivery.
3. **Scheduler/worker**: polls Reddit per subscription and hands eligible posts to the delivery service.

They can be split into separate containers later; all state lives in PostgreSQL, so no component depends on in-memory state for correctness.

## Layers (dependencies point downward only)
    bot/ , api/ , dashboard/        <- interfaces (thin: validate, authorize, delegate)
    services/                       <- business logic (feed, delivery, subscription limits, scheduler)
    reddit/                         <- isolated Reddit API client (OAuth, rate limiting, media parsing)
    database/ (models, repos)       <- persistence; every query is scoped by guild_id
    security/ , config/             <- cross-cutting (crypto, settings, redacting logs)

## Delivery pipeline & idempotency
load active subscriptions -> fetch new posts -> validate + SFW filter -> **claim** (INSERT into
`delivery_records` with UNIQUE(reddit_post_id, destination_id); conflict = already handled) -> send embed ->
mark sent/failed -> retry with backoff on retryable errors. Claiming *before* sending prevents duplicates
across restarts and concurrent workers; a stale-claim sweep recovers crashes between claim and send.

## Tenant isolation
Every tenant-owned table carries `guild_id`. Repositories require a guild id and never expose unscoped queries.
Dashboard routes authorize by checking the session user's `MANAGE_GUILD` membership for that guild on every
request (never trusting a guild id from the client alone). Owner-only routes check `DISCORD_OWNER_IDS`.

## Content policy
SFW only: posts flagged `over_18` are never delivered. Videos are delivered as links/embeds, not re-uploaded.

## Items requiring manual verification (not assumed)
- Reddit API access/approval and current rate-limit terms under Reddit's Data API Terms.
- Discord application settings, privileged intents (none are planned), and bot permissions.
- Legal text (Privacy Policy / ToS) must be reviewed by you before public launch.
- Any payment provider is out of scope until you choose and configure one.

## Phase map
1 foundation (done) · 2 Discord bot/OAuth · 3 Reddit client · 4 monitoring · 5 media delivery ·
6 PostgreSQL/multi-tenant · 7 slash commands · 8 dashboard · 9 plans/usage · 10 security hardening/tests ·
11 Docker/VPS · 12 docs/launch prep.
