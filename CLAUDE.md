# Telemt — MTProxy Telegram Bot

## Project Overview
Telegram bot that sells MTProxy subscriptions with YooKassa payment integration.
Users buy 30-day proxy access, bot creates proxy secrets via telemt API and sends tg://proxy links.

## Server
- **IP**: 82.148.28.80
- **SSH**: `ssh root@82.148.28.80`
- **Project path on server**: `/opt/telemt/bot/`
- **Deploy**: `cd /opt/telemt/bot && docker compose build && docker compose up -d`
- **Logs**: `docker logs bot-bot-1 --tail 50`
- **Local project** (Windows): `C:\opt\telemt` — edit here, scp to server, rebuild

## Architecture
- **Runtime**: Python 3.12 in Docker, `network_mode: host`
- **Framework**: aiogram 3.x (long polling), aiohttp (YooKassa webhook server on port 8080)
- **Database**: SQLite via aiosqlite, stored at `/app/data/bot.db` (mounted `./data`)
- **Scheduler**: APScheduler — cleans up expired subscriptions every 5 min
- **Payments**: YooKassa (test mode), webhook at `/yookassa/webhook` — needs HTTPS domain to work
- **Proxy backend**: telemt API at `http://127.0.0.1:9091`

## Key Files
```
bot/
├── main.py          # Entry point: init DB, start bot polling + webhook server
├── config.py        # Env vars loader
├── handlers.py      # Telegram command/callback handlers
├── payment.py       # YooKassa payment creation
├── webhook.py       # aiohttp server for YooKassa webhook notifications
├── db.py            # SQLite schema + CRUD (users, subscriptions, payments)
├── proxy_manager.py # telemt API client (add/remove secrets)
├── secret_gen.py    # FakeTLS secret generation
├── scheduler.py     # Expired subscription cleanup
├── .env             # Secrets — DO NOT COMMIT
└── docker-compose.yml
```

## DB Tables
- `users` (telegram_id, username, created_at)
- `subscriptions` (telegram_id, secret, username, created_at, expires_at, active)
- `payments` (telegram_id, yookassa_payment_id, amount, status, created_at)

## Flow
1. User presses "Купить прокси" → bot creates YooKassa payment, shows pay link
2. User pays → YooKassa sends webhook → bot creates proxy via telemt API → sends tg://proxy link
3. Scheduler checks every 5 min for expired subscriptions, removes secrets, notifies users

## Notes
- Premium custom emoji used in messages (tg-emoji HTML tags). IDs in `/emodji` file at repo root.
- YooKassa webhook requires HTTPS — blocked until domain with SSL is set up.
- Bot uses only two premium emoji: ⚡ (header) and 🔗 (connect, for proxy links).
