# SAINI DRM Bot

A Telegram bot that downloads videos, PDFs, and other media from text/URL files and uploads them to Telegram. Includes a simple Flask web frontend as a keepalive/landing page.

## Architecture

- **Flask Web App** (`app.py`): Serves a simple landing page on port 5000
- **Telegram Bot** (`modules/main.py`): Main bot entry point, registers all handlers
- **modules/**: All bot logic split into separate handler modules
- **Entry point**: `start.sh` — starts Flask app in background then runs the bot

## Key Modules

- `vars.py` — Configuration via environment variables (with hardcoded fallback)
- `globals.py` — Shared mutable bot state
- `drm_handler.py` — Main download/DRM processing handler
- `youtube_handler.py` — YouTube download handlers
- `text_handler.py` — Text file processing
- `html_handler.py` — HTML file handling
- `broadcast.py` — Broadcast to all users
- `authorisation.py` — Auth user management
- `settings.py` — Bot settings management
- `settings_persistence.py` — Persists settings to `bot_settings.json`
- `saini.py` — Shared utility functions
- `utils.py` — Progress bar and formatting utilities
- `logs.py` — Logging setup
- `features.py` — Feature info handlers
- `commands.py` — Command listing handlers
- `upgrade.py` — Upgrade/subscription handlers

## Required Environment Secrets

| Secret | Description |
|--------|-------------|
| `API_ID` | Telegram API ID from my.telegram.org/apps |
| `API_HASH` | Telegram API Hash from my.telegram.org/apps |
| `BOT_TOKEN` | Bot token from @BotFather |
| `OWNER` | Your Telegram user ID |

## Optional Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `CREDIT` | `SAINI BOTS` | Bot credit name |
| `API_URL` | `""` | External API URL |
| `API_TOKEN` | `""` | External API token |
| `TOKEN_CP` | `""` | CP token |
| `ADDA_TOKEN` | `""` | ADDA token |
| `PHOTOLOGO` | iili.io URL | Logo photo URL |
| `PHOTOYT` | iili.io URL | YouTube photo URL |
| `PHOTOCP` | iili.io URL | CP photo URL |
| `PHOTOZIP` | iili.io URL | ZIP photo URL |

## Workflows

- **Start application**: `bash start.sh` — Starts Flask web app (port 5000, webview) and Telegram bot together

## Dependencies

Python packages: flask, gunicorn, pyrogram, pyrofork, pyromod, pytube, yt-dlp, aiohttp, aiofiles, pillow, TgCrypto, pycryptodome, beautifulsoup4, cloudscraper, ffmpeg-python, python-telegram-bot, motor, pytz, and more (see requirements.txt).

## Notes

- Bot session is stored in `bot.session` (auto-created by Pyrogram)
- Bot settings persisted in `bot_settings.json`
- Downloads go to `modules/downloads/` directory
- `vars.py` has hardcoded fallback credentials so the bot starts without env vars set
